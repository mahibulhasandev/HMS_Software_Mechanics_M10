# 🏥 Hospital Management System (HMS)

### A Modern, Modular & Scalable Hospital Management Platform

<p align="center">
  <strong>Developed by Software Mechanics</strong>
  <br/>
  <em>Academic Team Project — Moulvibazar Polytechnic Institute</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Django-5.2%2B-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"/>
  <img src="https://img.shields.io/badge/DRF-REST%20API-red?style=for-the-badge&logo=django" alt="DRF"/>
  <img src="https://img.shields.io/badge/PostgreSQL-17-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"/>
  <img src="https://img.shields.io/badge/Docker-Enabled-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"/>
</p>

---

## 📖 About The Project

The **Hospital Management System (HMS)** is a modular and scalable web-based healthcare management platform designed to simplify and digitize hospital operations.

The system aims to connect different hospital departments through a centralized platform, allowing efficient communication, data management, and operational coordination.

The project follows a modular architecture where each department manages its own responsibilities while sharing common resources and services.

### 🎯 Project Objectives

- Digitize hospital management operations.
- Centralize patient and hospital information.
- Improve communication between departments.
- Provide secure role-based access control.
- Reduce manual paperwork and operational complexity.
- Build a maintainable and scalable backend architecture.
- Provide RESTful APIs for frontend integration.

---

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend Programming Language |
| Django 5.2+ | Web Framework |
| Django REST Framework | REST API Development |
| PostgreSQL 17 | Relational Database |
| Docker | Containerization |
| Docker Compose | Multi-container Management |
| Git & GitHub | Version Control & Collaboration |
| DBeaver | Database Management |

---

## 🏗️ Project Architecture

The application follows a modular departmental architecture.

### Department Modules

| Module | Responsibility |
|---|---|
| Super Admin | Central administration and system management |
| Clinic | Outpatient and clinic operations |
| Diagnostic | Diagnostic and laboratory operations |
| Accounting | Financial and billing management |

*Additional modules can be integrated as the project evolves.*

### Architecture Principles

- Modular application structure.
- Separation of concerns.
- Reusable database relationships.
- Centralized authentication and authorization.
- RESTful API architecture.
- Scalable departmental integration.

---

## 📂 Project Structure

A suggested Django project structure:

```text
HMS_Software_Mechanics_M10/
│
├── apps/
│   ├── clinic/
│   ├── diagnostic/
│   ├── accounting/
│   └── super_admin/
│
├── config/
│   ├── settings/
│   ├── urls.py
│   └── wsgi.py
│
├── requirements.txt
├── manage.py
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

*The structure above is illustrative. Actual directories may differ as development progresses.*

---

# 🚀 Installation & Setup Guide

Follow the instructions below to run the project on your operating system.

## 1. Clone the Repository

Using HTTPS:

```bash
git clone https://github.com/mahibulhasandev/HMS_Software_Mechanics_M10.git
```

Or using SSH:

```bash
git clone git@github.com:mahibulhasandev/HMS_Software_Mechanics_M10.git
```

Navigate to the project directory:

```bash
cd HMS_Software_Mechanics_M10
```

## 2. Create Virtual Environment

### 🐧 Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 🍎 macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 🪟 Windows (PowerShell)

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate the environment again.

## 3. Install Dependencies

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install project requirements:

```bash
pip install -r requirements.txt
```

---

## ⚙️ Environment Configuration

Create your environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Example configuration:

```env
DEBUG=True

SECRET_KEY=your-secret-key

POSTGRES_DB=hms_database
POSTGRES_USER=admin
POSTGRES_PASSWORD=your_database_password
POSTGRES_HOST=postgres-db
POSTGRES_PORT=5432
```

**Important:**

- Never commit your actual `.env` file.
- Keep your `SECRET_KEY` private.
- Use strong database credentials.
- Set `DEBUG=False` in production.

Use the environment variable names expected by the project's settings.

---

# 🐳 Docker Setup

Docker is recommended for running PostgreSQL and other required services consistently across development environments.

### 1. Check Docker Installation

```bash
docker --version
docker compose version
```

### 2. Build and Start Containers

```bash
docker compose up --build -d
```

### 3. Check Running Containers

```bash
docker compose ps
```

### 4. View Container Logs

```bash
docker compose logs -f
```

### 5. Stop Containers

```bash
docker compose down
```

To remove containers and volumes:

```bash
docker compose down -v
```

**Warning:** The `-v` option deletes associated database volumes and can permanently remove stored database data.

---

## 🗄️ Database Migration

After configuring PostgreSQL and environment variables, execute the following commands.

### Create Migrations

```bash
python manage.py makemigrations
```

### Apply Migrations

```bash
python manage.py migrate
```

### Show Migration Status

```bash
python manage.py showmigrations
```

### Create Superuser

```bash
python manage.py createsuperuser
```

---

## ▶️ Run Development Server

Start the Django development server:

```bash
python manage.py runserver
```

The application will be available at:

```text
http://127.0.0.1:8000/
```

Django Admin:

```text
http://127.0.0.1:8000/admin/
```

---

# 🌿 Git Workflow & Branch Strategy

We follow a feature-based Git workflow to maintain code quality and avoid conflicts during team collaboration.

### Branch Structure

| Branch | Purpose |
|---|---|
| `main` | Production-ready and protected code |
| `develop` | Integration and development branch |
| `clinic` | Clinic department development |
| `diagnostic` | Diagnostic department development |
| `feature/accounting` | Accounting module development |
| `super-admin` | Super Admin module development |

### Development Workflow

```text
                 main
                  │
                  │ Protected
                  │
                develop
                  │
        ┌─────────┼──────────┐
        │         │          │
      clinic   diagnostic  super-admin
        │         │          │
        └─────────┼──────────┘
                  │
             Pull Requests
                  │
                develop
                  │
             Final Review
                  │
                 main
```

### Basic Git Commands

**1. Get the latest changes**

```bash
git fetch --all
git pull origin develop
```

**2. Switch to your feature branch**

```bash
git switch clinic
```

**3. Create a new feature branch**

```bash
git switch -c feature/your-feature-name
```

**4. Check your changes**

```bash
git status
```

**5. Stage and commit**

```bash
git add .
git commit -m "feat: add clinic management functionality"
```

**6. Push your branch**

```bash
git push -u origin feature/your-feature-name
```

**7. Create a Pull Request**

Create a Pull Request on GitHub targeting `develop`.

### Commit Message Convention

We recommend following Conventional Commits:

| Prefix | Purpose |
|---|---|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation |
| `refactor:` | Code refactoring |
| `style:` | Formatting changes |
| `test:` | Adding or updating tests |
| `chore:` | Maintenance tasks |

Examples:

```bash
git commit -m "feat: add patient registration API"
git commit -m "fix: resolve clinic appointment validation"
git commit -m "docs: update installation guide"
```

### 🔒 Main Branch Protection

The `main` branch is protected.

- Direct changes should go through Pull Requests.
- At least one approval is required where configured.
- Force pushes are blocked.
- Branch deletion is restricted.
- Review conversations must be resolved before merging where configured.

---

# 🧪 Testing

Run the Django test suite:

```bash
python manage.py test
```

For a specific application:

```bash
python manage.py test apps.clinic
```

---

# 🔧 Troubleshooting

### PostgreSQL Connection Error

- Ensure PostgreSQL is running.
- Verify database credentials.
- Check `POSTGRES_HOST` and `POSTGRES_PORT`.
- Verify Docker container status.

### Migration Conflicts

Check migration status:

```bash
python manage.py showmigrations
```

Inspect migration history and coordinate with your team before creating or deleting migration files.

### Port Already in Use

Check which process is using the port:

```bash
sudo lsof -i :8000
```

Run Django on another port:

```bash
python manage.py runserver 8001
```

### Docker Container Issues

```bash
docker compose ps
docker compose logs
```

---

# 👨‍💻 Development Team

<p align="center">
  <strong>SOFTWARE MECHANICS</strong>
  <br/>
  <em>Building reliable software through collaboration.</em>
</p>

This project is developed collaboratively as an academic team project.

**Project Lead:** Mahibul Hasan

**Repository:** [HMS_Software_Mechanics_M10](https://github.com/mahibulhasandev/HMS_Software_Mechanics_M10)

**GitHub:** [@mahibulhasandev](https://github.com/mahibulhasandev)

---

# 🤝 Contribution Guidelines

We welcome contributions from all project team members.

1. Always pull the latest changes from `develop`.
2. Work on your assigned feature branch.
3. Follow the existing coding conventions.
4. Write meaningful commit messages.
5. Test your changes before pushing.
6. Create a Pull Request targeting `develop`.
7. Resolve review comments before requesting a merge.

Please coordinate with the project lead before making changes to shared models, authentication, or common database relationships.

---

# 📜 License

This project is developed for academic and educational purposes.

See the [LICENSE](LICENSE) file for licensing information, if included.

---

<p align="center">
  <strong>🏥 Hospital Management System</strong>
  <br/>
  Developed with ❤️ by <strong>Software Mechanics</strong>
  <br/>
  <sub>© 2026 Software Mechanics. All rights reserved.</sub>
</p>