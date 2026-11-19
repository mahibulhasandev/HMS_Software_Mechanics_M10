🏥 HMS – Hospital Management System

A Django-based Hospital Management System developed by Software Mechanics – M10.

This project aims to digitize hospital operations, manage departments, and simplify healthcare-related activities through a centralized web-based platform.

🚀 Technology Stack

- Backend: Python, Django, Django REST Framework
- Database: PostgreSQL
- Containerization: Docker & Docker Compose
- Version Control: Git & GitHub
- Environment: Python Virtual Environment (venv)

📁 Project Repository

GitHub Repository:
"git@github.com:mahibulhasandev/HMS_Software_Mechanics_M10.git"

📋 Prerequisites

Install the following tools before starting:

- Python 3.12+
- Git
- Docker Desktop / Docker Engine
- Docker Compose
- PostgreSQL (optional if using Docker)

1. Clone Repository

git clone git@github.com:mahibulhasandev/HMS_Software_Mechanics_M10.git

cd HMS_Software_Mechanics_M10

2. Create Virtual Environment

Choose the command according to your operating system.

🪟 Windows (PowerShell / CMD)

python -m venv .venv

Activate:

PowerShell:

.venv\Scripts\Activate.ps1

CMD:

.venv\Scripts\activate.bat

🍎 macOS

python3 -m venv .venv
source .venv/bin/activate

🐧 Linux

python3 -m venv .venv
source .venv/bin/activate

3. Install Dependencies

Upgrade pip:

python -m pip install --upgrade pip

Install project requirements:

pip install -r requirements.txt

4. Environment Configuration

Create a ".env" file in the project root directory.

Example:

SECRET_KEY=your-secret-key
DEBUG=True

DB_NAME=hms_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

Note: Adjust environment variable names according to your Django settings. Never commit your actual ".env" file to GitHub.

5. Docker Setup (PostgreSQL)

Make sure Docker is running.

Build and start containers:

docker compose up --build -d

Check running containers:

docker compose ps

View container logs:

docker compose logs -f

Stop containers:

docker compose down

Stop containers and remove database volumes:

docker compose down -v

Warning: "docker compose down -v" deletes persistent database volume data.

6. Database Migrations

After starting PostgreSQL, run:

python manage.py makemigrations

Apply migrations:

python manage.py migrate

Check migration status:

python manage.py showmigrations

7. Create Superuser

Create an admin account:

python manage.py createsuperuser

Follow the instructions to configure your admin credentials.

8. Run Development Server

Start Django:

python manage.py runserver

Open in browser:

- Application: http://127.0.0.1:8000/
- Django Admin: http://127.0.0.1:8000/admin/

9. Useful Django Commands

Command| Description
"python manage.py check"| Check project configuration
"python manage.py makemigrations"| Create migrations
"python manage.py migrate"| Apply migrations
"python manage.py showmigrations"| Show migration status
"python manage.py createsuperuser"| Create admin account
"python manage.py runserver"| Start development server
"python manage.py collectstatic"| Collect static files
"python manage.py shell"| Open Django shell
"python manage.py test"| Run tests

10. Useful Docker Commands

Command| Description
"docker compose up -d"| Start containers
"docker compose up --build"| Build and start containers
"docker compose down"| Stop containers
"docker compose ps"| List containers
"docker compose logs -f"| View live logs
"docker compose restart"| Restart services
"docker compose down -v"| Remove containers and volumes
"docker volume ls"| List Docker volumes

11. Git Workflow

Check current branch:

git branch

Create a new branch:

git checkout -b feature/your-feature-name

Switch branch:

git switch main

Pull latest changes:

git pull origin main

Check changes:

git status

Stage changes:

git add .

Commit changes:

git commit -m "Add your changes"

Push branch:

git push -u origin feature/your-feature-name

12. Development Workflow

Recommended workflow for contributors:

1. Clone the repository.
2. Create and activate a virtual environment.
3. Install project dependencies.
4. Configure the ".env" file.
5. Start PostgreSQL using Docker Compose.
6. Create and apply database migrations.
7. Create a superuser if needed.
8. Run the Django development server.
9. Create a separate Git branch for your task.
10. Commit and push your changes.

👨‍💻 Development Team

Project: Hospital Management System
Team: Software Mechanics – M10
Repository: mahibulhasandev/HMS_Software_Mechanics_M10

---

Note: This project is currently under active development. Setup instructions and features may change as development progresses.
