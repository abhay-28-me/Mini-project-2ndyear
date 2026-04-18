# KeyAuth — Keystroke Dynamics Authentication

A biometric authentication system that uses **keystroke dynamics** to verify user identity. Instead of just a password, the system learns *how* you type — your rhythm, dwell times, and flight times between keys.

## How It Works

1. **Register** — Type your password 10 times. The system builds a personal typing profile.
2. **Login** — Type your password once. The system compares your typing rhythm against your enrolled profile.
3. **Continuous Learning** — Every successful login improves your personal model automatically.

### Authentication Layers

| Layer | Method | Purpose |
|-------|--------|---------|
| 1 | IKDD-trained Random Forest | Blocks bots and random input |
| 2 | Z-score profile matching | Verifies it's specifically YOU typing |

### Adaptive Threshold

The system gets stricter as it learns more about your typing:

| Logins | Threshold |
|--------|-----------|
| 0–15 | 2.5 (lenient) |
| 16–30 | 2.0 |
| 31–50 | 1.8 |
| 50+ | 1.5 (tight) |

---

## Project Structure

```
KeyAuth/
│
├── app.py                 # Flask application
├── database.py            # SQLite user management
├── reset_user.py          # Admin utility to reset users
├── requirements.txt       # Python dependencies
├── gunicorn_conf.py       # Production server config
│
├── model/
│   ├── __init__.py
│   ├── parse_ikdd.py      # Feature extraction (30 features)
│   ├── train_base.py      # Base model training script
│   └── enroll.py          # Enrollment & authentication logic
│
├── static/
│   └── js/
│       └── keystroke.js   # Browser keystroke capture
│
└── templates/
    ├── base.html
    ├── index.html
    ├── register.html
    ├── login.html
    └── dashboard.html
```

---

## Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/keyauth.git
cd keyauth
```

### 2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate      # macOS/Linux
venv\Scripts\activate         # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Add IKDD dataset
Download the [IKDD dataset](https://www.cse.iitk.ac.in/users/sandeeps/keystroke/) and place the `.txt` files in:
```
data/ikdd/
```

### 5. Train the base model (once only)
```bash
python model/train_base.py
```

### 6. Run the app
```bash
# Development
python app.py

# Production
gunicorn -c gunicorn_conf.py app:app
```

Open your browser at `http://localhost:5000`

---

## Admin Utilities

```bash
# List all registered users
python reset_user.py --list

# Reset a specific user (clears DB + profile)
python reset_user.py username
```

---

## Tech Stack

- **Backend** — Python, Flask
- **ML** — scikit-learn (Random Forest), numpy, scipy
- **Database** — SQLite
- **Frontend** — Vanilla JS, HTML/CSS
- **Dataset** — IKDD (Indian Keystroke Dynamics Dataset)

---

## Security Features

- Password hashing with salt (SHA-256)
- Server-side session management
- Rate limiting (10 login attempts/min, 5 registrations/hour)
- Account lockout on repeated password failures
- Keystroke biometric as second factor