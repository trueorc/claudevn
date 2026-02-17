"""Data models - has circular import issue with app.py."""

from app import calculate_user_stats  # Circular import!


class User:
    """User model."""
    
    def __init__(self, email, name, phone=None):
        self.id = None
        self.email = email
        self.name = name
        self.phone = phone
    
    def save(self):
        """Save user to database (simplified)."""
        # In real app, would use ORM
        pass
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "phone": self.phone
        }
    
    def get_stats(self):
        """Get user statistics - uses circular import."""
        return calculate_user_stats(self.id)
    
    @staticmethod
    def query():
        """Query interface (simplified)."""
        return UserQuery()


class UserQuery:
    """Simplified query interface."""
    
    def filter_by(self, **kwargs):
        return self
    
    def first(self):
        return None


class Product:
    """Product model."""
    
    def __init__(self, name, price, stock):
        self.id = None
        self.name = name
        self.price = price
        self.stock = stock
    
    def save(self):
        """Save product to database (simplified)."""
        pass
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "price": self.price,
            "stock": self.stock
        }
    
    @staticmethod
    def query():
        """Query interface (simplified)."""
        return ProductQuery()


class ProductQuery:
    """Simplified query interface."""
    
    def get(self, product_id):
        # Simplified - would query database
        return None

