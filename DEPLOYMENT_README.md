# Smart Scheduler - Hybrid Voice/Text Interface

This version supports both speech and text input for maximum flexibility.

## 🚀 Quick Start

### Backend Setup
```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --reload
```

### Frontend Setup
```bash
cd frontend
npm install
npm start
```

## 🎯 Features

### Input Modes:
- **Text Mode**: Traditional chat interface
- **Speech Mode**: Voice input with real-time transcription
- **Toggle**: Switch between modes seamlessly

### Capabilities:
- ✅ Natural language scheduling
- ✅ Calendar integration
- ✅ Smart slot suggestions
- ✅ Availability checking
- ✅ Meeting confirmation
- ✅ User preference learning

## 🛠️ Architecture

```
Frontend (React)          Backend (FastAPI)
├── Speech Recognition ←→  ├── Gemini LLM
├── Text Input         ←→  ├── Google Calendar
├── Visual Calendar    ←→  ├── Smart Scheduling
└── UI Controls        ←→  └── Session Management
```

## 📱 Usage Examples

### Text Input:
- "Schedule a 30-minute meeting tomorrow afternoon"
- "Am I free this Friday morning?"
- "Book a call with the team next week"

### Speech Input:
- Click microphone → Speak naturally → Auto-processed
- Real-time transcription
- Same natural language understanding

## 🔧 Configuration

1. **Environment Variables**: Copy `.env` from root project
2. **Google Calendar**: Ensure `credentials.json` is in backend folder
3. **CORS**: Frontend runs on `localhost:3000`, backend on `localhost:8000`

## 🌟 Benefits

### For Users:
- **Accessibility**: Choose input method based on situation
- **Speed**: Voice is faster for complex requests
- **Precision**: Text for specific details
- **Convenience**: Works on any device

### For Deployment:
- **Scalable**: Web-based, multi-user ready
- **Modern**: React + FastAPI stack
- **Responsive**: Mobile-friendly interface
- **Professional**: Enterprise-ready architecture

## 🚀 Next Steps

1. **Run both servers**
2. **Test speech/text switching**
3. **Try scheduling meetings**
4. **Check calendar integration**
