# Lab Management System

A comprehensive, Flask-based web application for managing and booking laboratory resources, including equipment, workplaces, and entire labs. This system is designed with role-based access control to cater to the different needs of students, supervisors, professors, and administrators.

## Features

*   **Role-Based Access Control:** Pre-defined roles (Student, Supervisor, Professor, Admin) with distinct permissions for viewing, booking, and managing resources.
*   **Consolidated Booking System:** A unified interface for booking lab resources. Users select a study, and the system intelligently presents available locations and equipment.
*   **Flexible Booking Scope:** Users can book an entire lab, all workplaces assigned to a study, or select individual workplaces for a single booking request.
*   **Study & Inventory Management:**
    *   Create and manage studies, associating them with specific labs, workplaces, and dedicated equipment.
    *   Conflict management prevents dedicating the same equipment to multiple studies with overlapping dates.
    *   A dynamic inventory system that can be populated from an Excel file.
*   **Admin & Supervisor Dashboard:**
    *   Approve new user accounts and manage existing user roles.
    *   Approve or reject pending booking requests.
    *   Pause/unpause labs, workplaces, and equipment for maintenance, with automatic cancellation of conflicting future bookings.
*   **Global Calendar:** A clear, consolidated calendar view of all approved bookings, study periods, and maintenance blocks.
*   **Automated Email Notifications:**
    *   User registration and approval status updates.
    *   Password reset functionality.
    *   Booking confirmations with iCal calendar invites.
    *   Notifications to supervisors for pending approvals.

## Tech Stack

*   **Backend:** Python, Flask, Flask-SQLAlchemy
*   **Database:** SQLite
*   **Frontend:** HTML, CSS, JavaScript, Bootstrap 5
*   **Libraries:** FullCalendar.js, Flatpickr.js, iCalendar

## Setup and Installation

Follow these steps to get the application running locally.

### 1. Prerequisites

*   Python 3.8 or newer
*   `pip` (Python package installer)

### 2. Clone the Repository

```bash
git clone <your-repository-url>
cd <repository-folder>
```

### 3. Set Up a Virtual Environment

It's highly recommended to use a virtual environment to manage project dependencies.

```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies

Install all the required Python packages from the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

### 5. Configure Email (Optional)

The application sends emails for notifications. To enable this, you must set two environment variables.

*   **`SMTP_USERNAME`**: Your Gmail address (e.g., `your-email@gmail.com`).
*   **`SMTP_PASSWORD`**: A Google App Password for your account.

```bash
# Windows (Command Prompt)
set SMTP_USERNAME="your-email@gmail.com"
set SMTP_PASSWORD="your-google-app-password"

# macOS/Linux
export SMTP_USERNAME="your-email@gmail.com"
export SMTP_PASSWORD="your-google-app-password"
```

> **Note:** If these variables are not set, the application will run without errors but will skip sending emails and print a notification to the console instead.

### 6. Prepare the Database

The system can be populated with initial equipment data from an Excel file.

1.  Place your equipment data file, named `eeg_equipment_2025_RCSE (1).xlsx`, in the root directory of the project.
2.  Run the import script. This will create the `lab_db_v7.db` file and populate it with users, labs, and equipment from the Excel sheet.

```bash
python import_excel.py
```

### 7. Run the Application

```bash
python app.py
```

The application will be available at `http://127.0.0.1:5000`.

### Default Login Credentials

*   **Admin:** `admin@tu-ilmenau.de` / `pass123`
*   **Professor:** `prof@tu-ilmenau.de` / `pass123`