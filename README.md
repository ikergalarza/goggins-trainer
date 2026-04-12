# Goggins Trainer

AI personal trainer powered by Claude. Plans workouts based on your goals, tracks your progress, and integrates with Strava.

## Stack

- **Backend**: FastAPI + Python + PostgreSQL
- **Frontend**: React + Vite + TypeScript
- **AI**: Claude (Anthropic)
- **Integrations**: Strava API
- **Deploy**: Railway

## Local development

### Backend
```bash
cd backend
cp .env.example .env  # fill in your keys
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```
