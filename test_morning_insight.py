#!/usr/bin/env python3
"""
Unit tests for MorningInsightGenerator
Run with: python -m pytest test_morning_insight.py -v
Or simply: python test_morning_insight.py
"""

import unittest
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock, mock_open
from morning_insight import MorningInsightGenerator


class TestMorningInsightGenerator(unittest.TestCase):
    """Test cases for MorningInsightGenerator class."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Mock environment variables
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'GOOGLE_CREDENTIALS': '{}'}):
            self.generator = MorningInsightGenerator()
    
    def test_initialization(self):
        """Test that MorningInsightGenerator initializes correctly."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'GOOGLE_CREDENTIALS': '{}'}):
            generator = MorningInsightGenerator()
            self.assertEqual(generator.model, "gpt-5-mini")
            self.assertEqual(generator.work_threshold_hours, 2)
            self.assertEqual(generator.max_completion_tokens, 300)
            self.assertEqual(generator.temperature, 0.9)
            self.assertIsNotNone(generator.ist_tz)
    
    def test_get_today_date_formatted(self):
        """Test date formatting in IST timezone."""
        date_str = self.generator._get_today_date_formatted()
        # Format should be 'Day, Month Date, Year' (e.g., 'Wednesday, December 31, 2025')
        parts = date_str.split(', ')
        self.assertEqual(len(parts), 3)
        # Check it's a valid format
        try:
            datetime.strptime(date_str, "%A, %B %d, %Y")
        except ValueError:
            self.fail(f"Date format invalid: {date_str}")
    
    def test_get_current_time_ist(self):
        """Test current time formatting in IST."""
        time_str = self.generator._get_current_time_ist()
        # Format should contain 'IST' and time (e.g., '11:15 AM IST')
        self.assertIn('IST', time_str)
        self.assertTrue(any(c.isdigit() for c in time_str))
    
    @patch('morning_insight.build')
    def test_google_calendar_setup_failure(self, mock_build):
        """Test Google Calendar setup with missing credentials."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = MorningInsightGenerator()
            self.assertIsNone(generator.calendar_service)
    
    @patch.dict(os.environ, {'GOOGLE_CREDENTIALS': '{"invalid": "json"}'})
    def test_google_calendar_setup_invalid_json(self):
        """Test Google Calendar setup with invalid JSON."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'GOOGLE_CREDENTIALS': 'invalid'}):
            generator = MorningInsightGenerator()
            self.assertIsNone(generator.calendar_service)
    
    @patch('morning_insight.OpenAI')
    def test_generate_wisdom_success(self, mock_openai):
        """Test successful wisdom generation."""
        # Mock the OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test wisdom"))]
        
        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_openai_instance
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'GOOGLE_CREDENTIALS': '{}'}):
            generator = MorningInsightGenerator()
            wisdom = generator._generate_wisdom()
            self.assertEqual(wisdom, "Test wisdom")
    
    @patch('morning_insight.OpenAI')
    def test_generate_wisdom_fallback(self, mock_openai):
        """Test wisdom generation with fallback on API error."""
        # Mock the OpenAI to raise an exception
        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_openai_instance
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'GOOGLE_CREDENTIALS': '{}'}):
            generator = MorningInsightGenerator()
            wisdom = generator._generate_wisdom()
            # Should return fallback message
            self.assertIn("fresh opportunity", wisdom.lower())
    
    @patch('morning_insight.OpenAI')
    def test_generate_work_insight_success(self, mock_openai):
        """Test successful work insight generation."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Work insight"))]
        
        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_openai_instance
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'GOOGLE_CREDENTIALS': '{}'}):
            generator = MorningInsightGenerator()
            insight = generator._generate_work_insight()
            self.assertEqual(insight, "Work insight")
    
    @patch('morning_insight.OpenAI')
    def test_generate_rest_insight_success(self, mock_openai):
        """Test successful rest insight generation."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Rest insight"))]
        
        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_openai_instance
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'GOOGLE_CREDENTIALS': '{}'}):
            generator = MorningInsightGenerator()
            insight = generator._generate_rest_insight()
            self.assertEqual(insight, "Rest insight")
    
    @patch('morning_insight.OpenAI')
    def test_generate_morning_insight(self, mock_openai):
        """Test complete morning insight generation."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test content"))]
        
        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_openai_instance
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'GOOGLE_CREDENTIALS': '{}'}):
            generator = MorningInsightGenerator()
            insight = generator.generate_morning_insight()
            
            # Check output contains required elements
            self.assertIn("AI-Generated Morning Insights", insight)
            self.assertIn("Daily Wisdom", insight)
            self.assertIn("Today's Focus", insight)
            self.assertIn("IST", insight)
            self.assertIn("GPT-5 mini", insight)
    
    def test_save_to_log(self):
        """Test log file creation."""
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('os.makedirs'):
                result = self.generator.save_to_log("Test content")
                # Should return a filename
                self.assertIsNotNone(result)
                # Should contain 'morning_insight' and timestamp
                self.assertIn("morning_insight", result)
                self.assertIn(".txt", result)
    
    def test_check_for_work_day_no_calendar(self):
        """Test work day check without calendar service."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'GOOGLE_CREDENTIALS': '{}'}):
            generator = MorningInsightGenerator()
            generator.calendar_service = None
            result = generator._check_for_work_day()
            self.assertFalse(result)
    
    def test_api_parameter_compatibility(self):
        """Test that the correct API parameters are used (max_completion_tokens, not max_tokens)."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'GOOGLE_CREDENTIALS': '{}'}):
            generator = MorningInsightGenerator()
            # Check that we use max_completion_tokens attribute
            self.assertEqual(generator.max_completion_tokens, 300)
            # Make sure max_tokens is not being used
            self.assertFalse(hasattr(generator, 'max_tokens') and generator.max_tokens != 300)


class TestIntegration(unittest.TestCase):
    """Integration tests for MorningInsightGenerator."""
    
    @patch('morning_insight.build')
    @patch('morning_insight.OpenAI')
    def test_full_workflow(self, mock_openai, mock_build):
        """Test complete workflow from initialization to log saving."""
        # Mock OpenAI
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Generated content"))]
        
        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_openai_instance
        
        # Mock Google Calendar
        mock_build.return_value = None
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'GOOGLE_CREDENTIALS': '{}'}), \
             patch('builtins.open', mock_open()), \
             patch('os.makedirs'):
            
            generator = MorningInsightGenerator()
            insight = generator.generate_morning_insight()
            log_file = generator.save_to_log(insight)
            
            # Verify workflow
            self.assertIsNotNone(insight)
            self.assertIsNotNone(log_file)
            self.assertIn("morning_insight", log_file)


def run_manual_tests():
    """
    Run tests with detailed output.
    This allows running the tests directly with: python test_morning_insight.py
    """
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestMorningInsightGenerator))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Status: {'✅ ALL TESTS PASSED' if result.wasSuccessful() else '❌ SOME TESTS FAILED'}")
    print("="*70)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_manual_tests()
    exit(0 if success else 1)
