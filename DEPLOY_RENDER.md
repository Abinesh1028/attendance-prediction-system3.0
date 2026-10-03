
# Public deployment

## Recommended: Render + GitHub

1. Create a GitHub repository named `attendance-prediction-system`.
2. Upload all files from this folder to the repository root.
3. On Render, choose **New → Web Service** and connect the GitHub repository.
4. Render will detect `render.yaml`, or you can enter:
   - Runtime: Python 3
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
5. Deploy.
6. Render provides a public HTTPS URL such as:
   `https://attendance-prediction-system.onrender.com`

The project already contains `render.yaml` and `requirements.txt`.

## Demo login

Username: `admin`
Password: `admin123`

## Important production note

The current project uses SQLite because it is simple for a college demo. On Render's free web service, the filesystem is ephemeral, so changes made to SQLite can disappear after a restart/redeploy. The supplied Excel dataset is automatically reseeded, so the demo can recover its initial sample data.

For a real system where attendance changes must permanently survive deployments, migrate the database to PostgreSQL or use a paid persistent disk. Do not use the demo password for a real deployment; replace it with an environment-based secret/authentication system before production use.

## Security checklist before real users

- Change the demo admin password.
- Use `SECRET_KEY` from an environment variable.
- Add proper password hashing (Werkzeug/bcrypt).
- Add CSRF protection.
- Add role-based permissions.
- Move student/attendance data to PostgreSQL.
- Validate and limit Excel uploads.
- Enable backups.
