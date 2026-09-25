# Radar stratégique — application web

Application interne de veille composée de `backend/` (API Flask et logique Radar) et `frontend/` (Next.js TypeScript).

## Développement local

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
python -m flask --app wsgi db upgrade
python -m flask --app wsgi seed-radars
python -m flask --app wsgi create-admin --name "Aymane"
python -m flask --app wsgi run --port 5000
```

Le dernier appel affiche une seule fois le code d’accès du premier administrateur. Seul son hash est conservé. Les accès suivants sont créés par un ADMIN dans « Utilisateurs & accès » ; il n’existe aucune inscription publique.

```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

## Déploiement

Render : Root Directory `backend`, Build Command `pip install -r requirements.txt`, Start Command `gunicorn wsgi:app --bind 0.0.0.0:$PORT`. Configurez `DATABASE_URL`, `SECRET_KEY`, `FRONTEND_URL` et les variables Radar/OpenAI.

Vercel : Root Directory `frontend`, framework Next.js, `NEXT_PUBLIC_API_URL=<origine Render>`.

La révision Alembic `31a4c96de702` ajoute uniquement les utilisateurs internes et l’audit d’authentification. Elle ne modifie aucune donnée Radar.
