
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_file
import sqlite3, os, io
from pathlib import Path
from functools import wraps
import pandas as pd
import numpy as np

try:
    from sklearn.ensemble import RandomForestClassifier
    SKLEARN = True
except Exception:
    SKLEARN = False

BASE = Path(__file__).resolve().parent
DB = BASE / "attendance.db"
XLSX = BASE / "Attendance_July_September_2026_Final.xlsx"
app = Flask(__name__)
app.secret_key = "attendance-prediction-demo-key-change-me"

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'student',
      roll_no TEXT
    );
    CREATE TABLE IF NOT EXISTS students(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      roll_no TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL DEFAULT 'Student',
      department TEXT DEFAULT 'CSE',
      year TEXT DEFAULT '2nd Year',
      section TEXT DEFAULT 'A'
    );
    CREATE TABLE IF NOT EXISTS attendance(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      student_id INTEGER NOT NULL,
      date TEXT NOT NULL,
      day TEXT,
      status TEXT NOT NULL CHECK(status IN ('P','A')),
      UNIQUE(student_id,date)
    );
    CREATE TABLE IF NOT EXISTS holidays(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL
    );
    """)
    # Demo admin account
    c.execute("INSERT OR IGNORE INTO users(username,password,role,roll_no) VALUES(?,?,?,?)",
              ("admin","admin123","admin",None))
    c.commit()
    c.close()

def seed_from_excel():
    c=conn()
    n=c.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    if n:
        c.close(); return
    if not XLSX.exists():
        c.close(); return
    df=pd.read_excel(XLSX, sheet_name="Attendance_Data")
    df["Date"]=pd.to_datetime(df["Date"])
    df["Status"]=df["Status"].astype(str).str.upper().str.strip()
    rollnos=sorted(df["Roll_No"].astype(str).unique())
    for r in rollnos:
        c.execute("INSERT OR IGNORE INTO students(roll_no,name) VALUES(?,?)",(r,f"Student {r}"))
    sid={row["roll_no"]:row["id"] for row in c.execute("SELECT id,roll_no FROM students")}
    rows=[]
    for _,r in df.iterrows():
        roll=str(r["Roll_No"]); d=r["Date"].strftime("%Y-%m-%d"); s="P" if r["Status"]=="P" else "A"
        rows.append((sid[roll],d,r["Day"],s))
    c.executemany("INSERT OR IGNORE INTO attendance(student_id,date,day,status) VALUES(?,?,?,?)",rows)
    # Useful sample holidays (editable in UI)
    for d,name in [("2026-08-15","Independence Day"),("2026-09-04","Krishna Jayanthi")]:
        c.execute("INSERT OR IGNORE INTO holidays(date,name) VALUES(?,?)",(d,name))
    c.commit(); c.close()

def setup():
    init_db(); seed_from_excel()

def login_required(f):
    @wraps(f)
    def w(*a,**kw):
        if "user" not in session: return redirect(url_for("login"))
        return f(*a,**kw)
    return w

def admin_required(f):
    @wraps(f)
    def w(*a,**kw):
        if session.get("role")!="admin": return redirect(url_for("dashboard"))
        return f(*a,**kw)
    return w

def classify(p):
    return "GOOD" if p>=85 else ("AVERAGE" if p>=75 else "RISK")

def stats_for(sid):
    c=conn()
    r=c.execute("""SELECT COUNT(*) total,
        SUM(CASE WHEN status='P' THEN 1 ELSE 0 END) present,
        SUM(CASE WHEN status='A' THEN 1 ELSE 0 END) absent
        FROM attendance WHERE student_id=?""",(sid,)).fetchone()
    c.close()
    total=r["total"] or 0; p=r["present"] or 0; a=r["absent"] or 0
    pct=round(p/total*100,2) if total else 0
    return {"total":total,"present":p,"absent":a,"percentage":pct,"status":classify(pct)}

def all_students():
    c=conn()
    rows=c.execute("SELECT * FROM students ORDER BY roll_no").fetchall()
    out=[]
    for r in rows:
        x=stats_for(r["id"])
        out.append(dict(r)|x)
    c.close(); return out

def features_for(sid):
    c=conn()
    rows=c.execute("SELECT date,status FROM attendance WHERE student_id=? ORDER BY date",(sid,)).fetchall()
    c.close()
    vals=[1 if r["status"]=="P" else 0 for r in rows]
    if not vals: return None
    total=len(vals); p=sum(vals)
    recent=vals[-10:]
    prev=vals[-5:]
    return np.array([p/total*100, sum(recent)/len(recent)*100,
                     sum(prev)/len(prev)*100, vals[-1],
                     sum(1 for x in vals[-5:] if x==0),
                     total],dtype=float)

def train_model():
    c=conn()
    students=c.execute("SELECT id FROM students").fetchall()
    X=[]; y=[]
    for r in students:
        f=features_for(r["id"])
        if f is None: continue
        # target: current attendance category, used as a prototype training target
        pct=f[0]
        X.append(f); y.append(2 if pct>=85 else (1 if pct>=75 else 0))
    c.close()
    if len(set(y))<2 or not SKLEARN: return None
    m=RandomForestClassifier(n_estimators=120,random_state=42,class_weight="balanced")
    m.fit(np.array(X),np.array(y)); return m

def predict_student(sid):
    f=features_for(sid)
    if f is None: return 0,"RISK"
    # Forecast baseline: weighted recent trend. RF class is used as a supporting signal.
    current=f[0]; recent=f[1]
    predicted=round(0.60*current+0.40*recent,2)
    model=train_model()
    if model is not None:
        pred_class=int(model.predict([f])[0])
        # Keep numeric forecast continuous; class is used only when the result is near a boundary.
        if abs(predicted-75)<2 or abs(predicted-85)<2:
            predicted = round(0.5*predicted + 0.5*({0:65,1:80,2:92}[pred_class]),2)
    return predicted,classify(predicted)

@app.route("/")
def home():
    return redirect(url_for("dashboard") if "user" in session else url_for("login"))

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=request.form.get("username","").strip()
        p=request.form.get("password","")
        c=conn(); row=c.execute("SELECT * FROM users WHERE username=? AND password=?",(u,p)).fetchone(); c.close()
        if row:
            session["user"]=row["username"]; session["role"]=row["role"]; session["roll_no"]=row["roll_no"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password","error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/api/overview")
@login_required
def api_overview():
    c=conn()
    q=c.execute("""SELECT COUNT(DISTINCT student_id) students, COUNT(*) records,
      SUM(status='P') present, SUM(status='A') absent,
      COUNT(DISTINCT date) classes FROM attendance""").fetchone()
    c.close()
    total=q["records"] or 0; p=q["present"] or 0
    pct=round(p/total*100,2) if total else 0
    return jsonify(dict(q)|{"percentage":pct,"status":classify(pct)})

@app.route("/api/trend")
@login_required
def api_trend():
    c=conn()
    rows=c.execute("""SELECT date,
      SUM(status='P') present,SUM(status='A') absent
      FROM attendance GROUP BY date ORDER BY date""").fetchall()
    c.close()
    return jsonify([dict(r) for r in rows])

@app.route("/students")
@login_required
def students_page(): return render_template("students.html")

@app.route("/api/students")
@login_required
def api_students(): return jsonify(all_students())

@app.route("/api/student/<roll>")
@login_required
def api_student(roll):
    c=conn(); s=c.execute("SELECT * FROM students WHERE roll_no=?",(roll,)).fetchone()
    if not s: c.close(); return jsonify({"error":"Student not found"}),404
    hist=c.execute("SELECT date,day,status FROM attendance WHERE student_id=? ORDER BY date DESC",(s["id"],)).fetchall()
    c.close()
    st=stats_for(s["id"]); pred,ps=predict_student(s["id"])
    return jsonify({"student":dict(s),"stats":st,"prediction":pred,"prediction_status":ps,"history":[dict(x) for x in hist]})

@app.route("/attendance",methods=["GET","POST"])
@login_required
@admin_required
def attendance_page():
    if request.method=="POST":
        roll=request.form["roll_no"]; date=request.form["date"]; status=request.form["status"]
        c=conn(); s=c.execute("SELECT id FROM students WHERE roll_no=?",(roll,)).fetchone()
        if s:
            day=pd.to_datetime(date).strftime("%A")
            c.execute("""INSERT INTO attendance(student_id,date,day,status) VALUES(?,?,?,?)
                      ON CONFLICT(student_id,date) DO UPDATE SET status=excluded.status,day=excluded.day""",
                      (s["id"],date,day,status))
            c.commit()
        c.close(); return redirect(url_for("attendance_page"))
    c=conn(); st=c.execute("SELECT roll_no,name FROM students ORDER BY roll_no").fetchall(); c.close()
    return render_template("attendance.html",students=st)

@app.route("/api/class-prediction")
@login_required
def api_class_prediction():
    rows=all_students(); out=[]
    for r in rows:
        pred,ps=predict_student(r["id"])
        out.append({"roll_no":r["roll_no"],"name":r["name"],"current":r["percentage"],"predicted":pred,"status":ps})
    return jsonify(out)

@app.route("/analytics")
@login_required
def analytics(): return render_template("analytics.html")

@app.route("/api/analytics")
@login_required
def api_analytics():
    c=conn()
    monthly=c.execute("""SELECT substr(date,1,7) month,
      SUM(status='P') present,SUM(status='A') absent,COUNT(*) total
      FROM attendance GROUP BY substr(date,1,7) ORDER BY month""").fetchall()
    c.close()
    students=all_students()
    return jsonify({"monthly":[dict(x)|{"percentage":round((x["present"] or 0)/(x["total"] or 1)*100,2)} for x in monthly],
                    "students":students})

@app.route("/calendar")
@login_required
def calendar(): return render_template("calendar.html")

@app.route("/api/calendar")
@login_required
def api_calendar():
    c=conn()
    rows=c.execute("""SELECT date,SUM(status='P') present,SUM(status='A') absent
                      FROM attendance GROUP BY date ORDER BY date""").fetchall()
    hol=c.execute("SELECT date,name FROM holidays ORDER BY date").fetchall(); c.close()
    return jsonify({"days":[dict(x) for x in rows],"holidays":[dict(x) for x in hol]})

@app.route("/holidays",methods=["GET","POST"])
@login_required
@admin_required
def holidays():
    if request.method=="POST":
        c=conn()
        try:
            c.execute("INSERT INTO holidays(date,name) VALUES(?,?)",(request.form["date"],request.form["name"]))
            c.commit()
        except sqlite3.IntegrityError: pass
        c.close()
    c=conn(); h=c.execute("SELECT * FROM holidays ORDER BY date").fetchall(); c.close()
    return render_template("holidays.html",holidays=h)

@app.route("/students/add",methods=["POST"])
@login_required
@admin_required
def add_student():
    c=conn()
    try:
        c.execute("INSERT INTO students(roll_no,name,department,year,section) VALUES(?,?,?,?,?)",
                  tuple(request.form.get(k,"") for k in ["roll_no","name","department","year","section"]))
        c.commit()
    except sqlite3.IntegrityError: pass
    c.close(); return redirect(url_for("students_page"))

@app.route("/import",methods=["POST"])
@login_required
@admin_required
def import_excel():
    file=request.files.get("file")
    if not file: return redirect(url_for("dashboard"))
    path=BASE/"uploaded_attendance.xlsx"; file.save(path)
    df=pd.read_excel(path)
    required={"Date","Roll_No","Status"}
    if not required.issubset(df.columns):
        path.unlink(missing_ok=True); flash("Excel must contain Date, Roll_No and Status columns.","error"); return redirect(url_for("dashboard"))
    df["Date"]=pd.to_datetime(df["Date"]); df["Status"]=df["Status"].astype(str).str.upper().str.strip()
    c=conn()
    for r in df["Roll_No"].astype(str).unique():
        c.execute("INSERT OR IGNORE INTO students(roll_no,name) VALUES(?,?)",(r,f"Student {r}"))
    sid={x["roll_no"]:x["id"] for x in c.execute("SELECT id,roll_no FROM students")}
    for _,r in df.iterrows():
        roll=str(r["Roll_No"]); d=r["Date"].strftime("%Y-%m-%d"); s="P" if r["Status"]=="P" else "A"
        c.execute("""INSERT INTO attendance(student_id,date,day,status) VALUES(?,?,?,?)
                     ON CONFLICT(student_id,date) DO UPDATE SET status=excluded.status,day=excluded.day""",
                  (sid[roll],d,r.get("Day",r["Date"].strftime("%A")),s))
    c.commit(); c.close(); path.unlink(missing_ok=True)
    flash("Attendance Excel imported successfully.","ok")
    return redirect(url_for("dashboard"))

@app.route("/report.csv")
@login_required
def report():
    rows=all_students()
    out=io.StringIO(); out.write("Roll No,Name,Present,Absent,Total,Attendance %,Prediction %,Status\n")
    for r in rows:
        pred,ps=predict_student(r["id"])
        out.write(f'{r["roll_no"]},{r["name"]},{r["present"]},{r["absent"]},{r["total"]},{r["percentage"]},{pred},{ps}\n')
    return send_file(io.BytesIO(out.getvalue().encode()),mimetype="text/csv",
                     as_attachment=True,download_name="attendance_prediction_report.csv")
init_db()
if __name__=="__main__":
    setup()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
