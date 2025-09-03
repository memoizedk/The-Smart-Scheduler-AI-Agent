import requests
import json

# Test the Smart Scheduler API
def test_api():
    base_url = "http://localhost:8000"
    
    print("🧪 Testing Smart Scheduler API...")
    
    # Test 1: Basic health check
    try:
        response = requests.get(f"{base_url}/")
        print(f"✅ Health check: {response.json()}")
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return
    
    # Test 2: Chat API with text input
    try:
        chat_data = {
            "message": "Hello, I want to schedule a meeting",
            "user_id": "test_user"
        }
        
        response = requests.post(f"{base_url}/api/chat/text", json=chat_data)
        result = response.json()
        
        print(f"✅ Chat API response: {result['response']}")
        print(f"📊 Conversation state: {result['conversation_state']}")
        
    except Exception as e:
        print(f"❌ Chat API failed: {e}")
    
    # Test 3: Another message
    try:
        chat_data = {
            "message": "I need a 30-minute meeting",
            "user_id": "test_user"
        }
        
        response = requests.post(f"{base_url}/api/chat/text", json=chat_data)
        result = response.json()
        
        print(f"✅ Follow-up response: {result['response']}")
        
    except Exception as e:
        print(f"❌ Follow-up failed: {e}")

if __name__ == "__main__":
    test_api()
