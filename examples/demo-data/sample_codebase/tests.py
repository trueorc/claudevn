"""Unit tests - incomplete coverage."""

import unittest
from utils import validate_email, validate_phone, sanitize_input, calculate_discount


class TestValidation(unittest.TestCase):
    """Test validation functions."""
    
    def test_validate_email_valid(self):
        """Test valid email."""
        self.assertTrue(validate_email("test@example.com"))
    
    def test_validate_email_invalid(self):
        """Test invalid email."""
        self.assertFalse(validate_email("invalid"))
        self.assertFalse(validate_email(""))
    
    def test_validate_phone_valid(self):
        """Test valid phone."""
        self.assertTrue(validate_phone("1234567890"))
        self.assertTrue(validate_phone("123-456-7890"))
    
    def test_validate_phone_invalid(self):
        """Test invalid phone."""
        self.assertFalse(validate_phone("123"))
        self.assertFalse(validate_phone("abc"))


class TestSanitization(unittest.TestCase):
    """Test sanitization functions."""
    
    def test_sanitize_input(self):
        """Test input sanitization."""
        result = sanitize_input("<script>alert('xss')</script>Hello")
        self.assertEqual(result, "alertxssHello")
    
    def test_sanitize_empty(self):
        """Test empty input."""
        result = sanitize_input("")
        self.assertEqual(result, "")


class TestCalculations(unittest.TestCase):
    """Test calculation functions."""
    
    def test_calculate_discount(self):
        """Test discount calculation."""
        result = calculate_discount(100, 10)
        self.assertEqual(result, 90.0)
    
    def test_calculate_discount_zero(self):
        """Test zero discount."""
        result = calculate_discount(100, 0)
        self.assertEqual(result, 100.0)


if __name__ == "__main__":
    unittest.main()

