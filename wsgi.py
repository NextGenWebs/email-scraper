"""
WSGI entry point for production servers (Gunicorn, uWSGI)
Usage: gunicorn wsgi:app
"""
from app import app

if __name__ == "__main__":
    app.run()
