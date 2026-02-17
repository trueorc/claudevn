"""Main application module with various code quality issues for demo purposes."""

import json
from models import User, Product
from utils import validate_email, validate_phone, sanitize_input, log_event


def process_request(request_data):
    """Process incoming request - intentionally long function with multiple responsibilities."""
    # Validate request
    if not request_data:
        return {"error": "No data provided"}
    
    if "email" not in request_data:
        return {"error": "Email required"}
    
    email = request_data["email"]
    if not validate_email(email):
        return {"error": "Invalid email"}
    
    # Check if user exists
    user = User.query.filter_by(email=email).first()
    
    if not user:
        # Create new user
        name = request_data.get("name", "")
        phone = request_data.get("phone", "")
        
        if not name:
            return {"error": "Name required for new users"}
        
        if phone and not validate_phone(phone):
            return {"error": "Invalid phone number"}
        
        user = User(
            email=email,
            name=name,
            phone=phone
        )
        user.save()
        log_event("user_created", {"email": email})
    
    # Process order if present
    if "order" in request_data:
        order_data = request_data["order"]
        
        if "products" not in order_data:
            return {"error": "No products in order"}
        
        products = order_data["products"]
        total = 0
        
        for product_id in products:
            product = Product.query.get(product_id)
            if not product:
                return {"error": f"Product {product_id} not found"}
            
            if product.stock < 1:
                return {"error": f"Product {product.name} out of stock"}
            
            total += product.price
            product.stock -= 1
            product.save()
        
        # Create order
        order = {
            "user_id": user.id,
            "products": products,
            "total": total,
            "status": "pending"
        }
        
        # Save order (simplified)
        with open(f"orders/{user.id}_{len(products)}.json", "w") as f:
            json.dump(order, f)
        
        log_event("order_created", {"user_id": user.id, "total": total})
        
        return {
            "success": True,
            "order_id": f"{user.id}_{len(products)}",
            "total": total
        }
    
    # Update user profile
    if "profile" in request_data:
        profile_data = request_data["profile"]
        
        if "name" in profile_data:
            user.name = sanitize_input(profile_data["name"])
        
        if "phone" in profile_data:
            phone = profile_data["phone"]
            if validate_phone(phone):
                user.phone = phone
            else:
                return {"error": "Invalid phone number"}
        
        user.save()
        log_event("profile_updated", {"user_id": user.id})
        
        return {"success": True, "user_id": user.id}
    
    return {"success": True, "user": user.to_dict()}


def get_user_orders(user_id):
    """Get all orders for a user."""
    import os
    orders = []
    
    # Read all order files (inefficient)
    for filename in os.listdir("orders"):
        if filename.startswith(f"{user_id}_"):
            with open(f"orders/{filename}") as f:
                order = json.load(f)
                orders.append(order)
    
    return orders


def calculate_user_stats(user_id):
    """Calculate statistics for a user."""
    orders = get_user_orders(user_id)
    
    total_spent = sum(order["total"] for order in orders)
    total_orders = len(orders)
    avg_order_value = total_spent / total_orders if total_orders > 0 else 0
    
    return {
        "total_spent": total_spent,
        "total_orders": total_orders,
        "avg_order_value": avg_order_value
    }

