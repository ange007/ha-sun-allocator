"""Test script for translation functionality."""
import os
import json
import logging

# Self-contained implementation of translation helper functions
def load_translations(language: str, domain: str = "sun_allocator"):
    """Load translations from a JSON file."""
    try:
        # Get the path to the translations directory
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        translation_file = os.path.join(base_dir, "translations", f"{language}.json")
        
        # Check if the file exists
        if not os.path.exists(translation_file):
            logger.warning(f"Translation file not found: {translation_file}")
            # Fall back to English if the requested language is not available
            if language != "en":
                return load_translations("en", domain)
            return {}
        
        # Load the translations from the file
        with open(translation_file, "r", encoding="utf-8") as f:
            translations = json.load(f)
            return translations
    except Exception as e:
        logger.error(f"Error loading translations: {e}")
        return {}

def get_translation(key, language="en", domain="sun_allocator", placeholders=None):
    """Get a translation by key."""
    try:
        # Load translations
        translations = load_translations(language, domain)
        
        # Split the key into parts
        parts = key.split(".")
        
        # Navigate through the translations dictionary
        value = translations
        for part in parts:
            if part in value:
                value = value[part]
            else:
                # Key not found, return the key itself
                return key
        
        # If the value is not a string, return the key
        if not isinstance(value, str):
            return key
        
        # Replace placeholders if provided
        if placeholders:
            for placeholder, replacement in placeholders.items():
                value = value.replace(f"{{{placeholder}}}", str(replacement))
        
        return value
    except Exception as e:
        logger.error(f"Error getting translation for key '{key}': {e}")
        return key

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_load_translations():
    """Test loading translations from files."""
    logger.info("Testing load_translations function...")
    
    # Test loading English translations
    en_translations = load_translations("en")
    if not en_translations:
        logger.error("Failed to load English translations")
        return False
    
    logger.info(f"Successfully loaded English translations with {len(en_translations)} keys")
    
    # Test loading Ukrainian translations
    uk_translations = load_translations("uk")
    if not uk_translations:
        logger.error("Failed to load Ukrainian translations")
        return False
    
    logger.info(f"Successfully loaded Ukrainian translations with {len(uk_translations)} keys")
    
    # Test fallback to English for non-existent language
    nonexistent_translations = load_translations("nonexistent")
    if not nonexistent_translations:
        logger.error("Failed to fallback to English for non-existent language")
        return False
    
    logger.info("Successfully fallback to English for non-existent language")
    
    return True

def test_get_translation():
    """Test getting translations by key."""
    logger.info("Testing get_translation function...")
    
    # Test getting English translations
    en_title = get_translation("config.step.user.title", "en")
    if en_title == "config.step.user.title":
        logger.error("Failed to get English translation for config.step.user.title")
        return False
    
    logger.info(f"English translation for config.step.user.title: {en_title}")
    
    # Test getting Ukrainian translations
    uk_title = get_translation("config.step.user.title", "uk")
    if uk_title == "config.step.user.title":
        logger.error("Failed to get Ukrainian translation for config.step.user.title")
        return False
    
    logger.info(f"Ukrainian translation for config.step.user.title: {uk_title}")
    
    # Test getting field label translations
    en_field = get_translation("config.field.pv_power", "en")
    if en_field == "config.field.pv_power":
        logger.error("Failed to get English translation for config.field.pv_power")
        return False
    
    logger.info(f"English translation for config.field.pv_power: {en_field}")
    
    # Test getting error message translations
    en_error = get_translation("config.error.invalid_vmp", "en")
    if en_error == "config.error.invalid_vmp":
        logger.error("Failed to get English translation for config.error.invalid_vmp")
        return False
    
    logger.info(f"English translation for config.error.invalid_vmp: {en_error}")
    
    # Test getting selector option translations
    en_option = get_translation("config.selector.panel_configuration.options.series", "en")
    if en_option == "config.selector.panel_configuration.options.series":
        logger.error("Failed to get English translation for config.selector.panel_configuration.options.series")
        return False
    
    logger.info(f"English translation for config.selector.panel_configuration.options.series: {en_option}")
    
    # Test placeholders
    en_title_with_placeholders = get_translation("config.step.device_name_type.title", "en", placeholders={"action": "Add", "device_name": "Test Device"})
    if "{action}" in en_title_with_placeholders or "{device_name}" in en_title_with_placeholders:
        logger.error("Failed to replace placeholders in English translation")
        return False
    
    logger.info(f"English translation with placeholders: {en_title_with_placeholders}")
    
    return True

def print_all_translations(language="en"):
    """Print all translations for a language."""
    logger.info(f"Printing all translations for {language}...")
    
    translations = load_translations(language)
    if not translations:
        logger.error(f"Failed to load translations for {language}")
        return
    
    # Print translations in a readable format
    print(json.dumps(translations, indent=2, ensure_ascii=False))

def main():
    """Run all tests."""
    logger.info("Starting translation tests...")
    
    if not test_load_translations():
        logger.error("load_translations test failed")
        return
    
    if not test_get_translation():
        logger.error("get_translation test failed")
        return
    
    logger.info("All tests passed!")
    
    # Uncomment to print all translations
    # print_all_translations("en")
    # print_all_translations("uk")

if __name__ == "__main__":
    main()