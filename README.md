
# Attendance Prediction System — Complete Website

## Included
- Flask full-stack web application
- SQLite database
- Admin login
- Student management
- Attendance entry/update
- Excel import
- Student-level prediction
- Whole-class prediction
- Analytics and Chart.js graphs
- Attendance calendar
- Holiday management
- CSV prediction report
- Responsive UI
- Supplied July–September 2026 Excel dataset preloaded

## Run on Windows
1. Install Python 3.9+.
2. Extract this ZIP.
3. Open Command Prompt in the extracted folder.
4. Run:
   `py -m pip install -r requirements.txt`
5. Run:
   `py app.py`
6. Open:
   `http://127.0.0.1:5000`

## Demo login
Username: admin
Password: admin123

## Excel format
For import, the workbook should contain:
- Date
- Roll_No
- Status
Optional:
- Day

Status should be P for Present or A for Absent.

## ML note
The application includes a Random Forest classifier when scikit-learn is available, while the continuous attendance forecast combines overall and recent attendance rates. This is a project prototype, not a production-grade predictive model. For a stronger academic ML evaluation, split historical data chronologically into train/test sets and report accuracy, precision, recall, F1, and confusion matrix.

## Reset database
Delete `attendance.db` and restart `app.py`; the supplied Excel dataset will be seeded again.
