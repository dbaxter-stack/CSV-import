
import io
import re
import zipfile
from typing import Dict, Any, List, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="All-in-One School Data Builder", layout="wide")
st.title("📦 All-in-One School Data Builder")
st.caption("Upload your source spreadsheets on one page, then download a single ZIP containing every output.")

# ------------------------------
# Helpers
# ------------------------------
def _read_any(file) -> pd.DataFrame:
    name = file.name.lower()
    if name.endswith(".csv"):
        # Auto-detect delimiter
        try:
            return pd.read_csv(file, sep=None, engine="python")
        except Exception:
            file.seek(0)
            return pd.read_csv(file)
    # Excel: pick the first non-empty sheet
    xls = pd.ExcelFile(file)
    best_df = None
    max_rows = -1
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        rows = int(df.shape[0])
        if rows > max_rows and df.dropna(how="all").shape[0] > 0:
            best_df, max_rows = df, rows
    return best_df if best_df is not None else pd.read_excel(file)

def _infer_year_from_name(name: str) -> str:
    s = name.lower()
    m = re.search(r"(yr|year)[\s\-]?(\d{1,2})", s)
    return m.group(2) if m else ""

def _split_name(name: str) -> Tuple[str, str]:
    if pd.isna(name):
        return "", ""
    s = str(name).strip()
    if "," in s:
        last, first = s.split(",", 1)
        return first.strip(), last.strip()
    parts = s.split()
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]

def _map_rotation(v: Any) -> str:
    if pd.isna(v):
        return "WHOLE YEAR"
    s = str(v).strip()
    if not s:
        return "WHOLE YEAR"
    s_norm = re.sub(r"[;:/\s]+", ",", s)         # allow ; : / space as separators
    parts = [re.sub(r"[^0-9]", "", p) for p in s_norm.split(",") if p]
    setp = set([p for p in parts if p in {"1", "2", "3", "4"}])
    if setp == {"1", "2"}: return "SEMESTER 1"
    if setp == {"3", "4"}: return "SEMESTER 2"
    if setp == {"1"}: return "TERM 1"
    if setp == {"2"}: return "TERM 2"
    if setp == {"3"}: return "TERM 3"
    if setp == {"4"}: return "TERM 4"
    term_map = {"1": "TERM 1", "2": "TERM 2", "3": "TERM 3", "4": "TERM 4"}
    labels = [term_map.get(p, p) for p in parts]
    return ", ".join(sorted(set(labels))) if labels else "WHOLE YEAR"

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())

def _pick(df: pd.DataFrame, candidates: List[str]):
    # Try exact, case-insensitive, then contains-based fuzzy match.
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    cols = list(df.columns)
    lower_map = {c.lower(): c for c in cols}
    for c in candidates:
        if c in cols:
            return c
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    norm_map = {_norm(c): c for c in cols}
    for c in candidates:
        key = _norm(c)
        for nkey, orig in norm_map.items():
            if key and key in nkey:
                return orig
    for orig in cols:
        n = _norm(orig)
        if any(_norm(c) in n for c in candidates):
            return orig
    return None

def _series(df: pd.DataFrame, src_col: str, default: str = "") -> pd.Series:
    if src_col and src_col in df.columns:
        return df[src_col].astype(str)
    return pd.Series([default] * len(df), index=df.index, dtype="object")

# ------------------------------
# Conversions (your finalized specs)
# ------------------------------
def build_rooms(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["RoomCode"] = _series(df, _pick(df, ["Code"]))
    out["RoomName"] = _series(df, _pick(df, ["Notes"]))
    size_col = _pick(df, ["Size"])
    cap = pd.to_numeric(df.get(size_col, pd.Series([None]*len(df), index=df.index)), errors="coerce").fillna(0).astype(int)
    out["Capacity"] = cap
    return out[["RoomCode","RoomName","Capacity"]]

def build_teachers(df: pd.DataFrame, target_cols: List[str]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index, columns=target_cols)
    out["TeacherCode"] = _series(df, _pick(df, ["Code"]))
    name_col = _pick(df, ["Name"])
    if name_col:
        first, last = zip(*df[name_col].map(_split_name))
        out["FirstName"] = pd.Series(first, index=df.index, dtype="object")
        out["LastName"]  = pd.Series(last,  index=df.index, dtype="object")
    out["FacultyCode"] = _series(df, _pick(df, ["Faculty"]))
    out["HomeSpace"] = ""
    out["LearningSupport"] = ""
    return out

def build_students(files: List[Any], target_cols: List[str]) -> pd.DataFrame:
    frames = []
    for f in files:
        df = _read_any(f)
        yl = _infer_year_from_name(f.name)
        out = pd.DataFrame(index=df.index, columns=target_cols)
        out["StudentCode"] = _series(df, _pick(df, ["Code"]))
        name_col = _pick(df, ["Name"])
        if name_col:
            first, last = zip(*df[name_col].map(_split_name))
            out["FirstName"] = pd.Series(first, index=df.index, dtype="object")
            out["LastName"]  = pd.Series(last,  index=df.index, dtype="object")
        letter_col = _pick(df, ["Letter","CoreStudentBodyCode"])
        out["CoreStudentBodyCode"] = _series(df, letter_col)
        out["YearLevelCode"] = yl
        out["YearLevel"] = yl
        out["Curriculum"] = yl
        out["Gender"] = ""
        out["Email"] = _series(df, _pick(df, ["Email","E-mail","Email Address"]))
        frames.append(out)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=target_cols)

def build_class_memberships(files: List[Any]) -> pd.DataFrame:
    rows = []
    for f in files:
        df = _read_any(f)
        code_col = _pick(df, ["Code","StudentCode"])
        if not code_col:
            continue
        class_cols = [c for c in df.columns if re.match(r"(?i)^class[\s_]*\d+$", str(c).strip().replace(" ", "_"))]
        if not class_cols:
            class_cols = [c for c in df.columns if _norm("class") in _norm(str(c))]
        if not class_cols:
            continue
        long = df[[code_col] + class_cols].melt(id_vars=[code_col], var_name="src", value_name="ClassCode")
        long = long[long["ClassCode"].notna() & (long["ClassCode"].astype(str).str.strip() != "")]
        long["StudentCode"] = long[code_col].astype(str)
        rows.append(long[["StudentCode","ClassCode"]])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["StudentCode","ClassCode"])

def build_courses(files: List[Any], target_cols: List[str]) -> pd.DataFrame:
    frames = []
    for f in files:
        df = _read_any(f)
        yr = _infer_year_from_name(f.name)
        tmp = pd.DataFrame(index=df.index, columns=target_cols)
        cand_course = _pick(df, ["Course","CourseCode","Course Code"])
        cand_subject = _pick(df, ["Subject","CourseName","Course Name"])
        cand_faculty = _pick(df, ["Faculty","SubjectCode","Subject Code"])
        cand_rot = _pick(df, ["Rot","Rotation","RotationSet","Rotation Set"])
        cand_line = _pick(df, ["Line","Type"])
        tmp["CourseCode"] = _series(df, cand_course)
        tmp["CourseName"] = _series(df, cand_subject)
        tmp["CurriculumName"] = yr
        tmp["SubjectCode"] = _series(df, cand_faculty)
        tmp["RotationSet"] = _series(df, cand_rot).map(_map_rotation)
        tmp["Type"] = _series(df, cand_line).map(lambda x: "Core" if str(x).strip().lower().startswith("group") else "Elective")
        frames.append(tmp)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=target_cols)
    if "CourseCode" in out.columns:
        out = out[out["CourseCode"].astype(str).str.strip() != ""].drop_duplicates(subset=["CourseCode"], keep="first")
    return out[target_cols] if not out.empty else out

def build_classes_and_lessons(df: pd.DataFrame, courses_df: pd.DataFrame) -> pd.DataFrame:
    target_cols = ["PeriodCode","CourseCode","ClassIdentifier","TeacherCode","RoomCode","Rotation"]
    out = pd.DataFrame(index=df.index, columns=target_cols)
    cday = _pick(df, ["Day","DAY","day","DayName"])
    cper = _pick(df, ["Period","PERIOD","period","Per"])
    out["PeriodCode"] = (_series(df, cday, "") + _series(df, cper, ""))
    cclass = _pick(df, ["Class","ClassCode","Class Code","ClassIdentifier","Class Identifier"])
    cteach = _pick(df, ["TeacherCode","Teacher Code","Teacher","StaffCode","Staff Code","Staff"])
    croom = _pick(df, ["RoomCode","Room Code","Room","Rm","RM"])
    crot = _pick(df, ["Rotation","Rot","RotationSet","Rotation Set"])
    codes = sorted([str(x).strip() for x in courses_df.get("CourseCode", pd.Series(dtype=str)).dropna() if str(x).strip()], key=len, reverse=True)
    def split_class(val: Any) -> Tuple[str, str]:
        s = str(val) if pd.notna(val) else ""
        for code in codes:
            if s.startswith(code):
                rem = s[len(code):]
                rem = re.sub(r"^[\s\-\._/]+", "", rem)
                return code, rem
        return "", s
    if cclass:
        cc, ident = zip(*_series(df, cclass, "").map(split_class))
        out["CourseCode"] = pd.Series(cc, index=df.index, dtype="object")
        out["ClassIdentifier"] = pd.Series(ident, index=df.index, dtype="object")
    else:
        out["CourseCode"] = ""
        out["ClassIdentifier"] = ""
    out["TeacherCode"] = _series(df, cteach, "")
    out["RoomCode"]    = _series(df, croom, "")
    rot_lookup = courses_df.set_index("CourseCode")["RotationSet"] if (not courses_df.empty and "CourseCode" in courses_df.columns and "RotationSet" in courses_df.columns) else pd.Series(dtype=str)
    out["Rotation"] = out["CourseCode"].map(rot_lookup).fillna(_series(df, crot, ""))
    return out[target_cols]

# ------------------------------
# Upload UI (single page)
# ------------------------------
st.subheader("1) Upload sources")
col1, col2 = st.columns(2)
with col1:
    f_room = st.file_uploader("Room spreadsheet", type=["csv","xlsx","xls"], key="rooms")
    f_teacher = st.file_uploader("Teacher spreadsheet", type=["csv","xlsx","xls"], key="teachers")
    f_subjects = st.file_uploader("Subject CSV (static)", type=["csv"], key="subjects")
with col2:
    f_students = st.file_uploader("Student spreadsheets (multi)", type=["csv","xlsx","xls"], accept_multiple_files=True, key="students")
    f_courses = st.file_uploader("ClassData (Courses) — multi", type=["csv","xlsx","xls"], accept_multiple_files=True, key="courses")
    f_classes = st.file_uploader("Classes & Lessons spreadsheet", type=["csv","xlsx","xls"], key="classes")

st.subheader("2) Build outputs & download ZIP")
diagnostics = st.expander("🔎 Diagnostics (matched columns & row counts)")

if st.button("🧰 Build all files"):
    outputs: Dict[str, bytes] = {}

    # Rooms
    if f_room is not None:
        df_room = _read_any(f_room)
        rooms = build_rooms(df_room)
        outputs["ROOM.csv"] = rooms.to_csv(index=False).encode("utf-8")
        st.success(f"ROOM.csv ✓ ({len(rooms)} rows)")
        diagnostics.write({"rooms_rows": len(rooms), "room_cols": list(rooms.columns)})

    # Teachers
    if f_teacher is not None:
        df_teacher = _read_any(f_teacher)
        teacher_cols = ["TeacherCode","FirstName","LastName","FacultyCode","HomeSpace","LearningSupport"]
        teachers = build_teachers(df_teacher, teacher_cols)
        outputs["Teacher.csv"] = teachers.to_csv(index=False).encode("utf-8")
        st.success(f"Teacher.csv ✓ ({len(teachers)} rows)")
        diagnostics.write({"teachers_rows": len(teachers), "teacher_cols": list(teachers.columns)})

    # Courses (must be ready before Classes & Lessons)
    courses_df = pd.DataFrame(columns=["CourseCode","CourseName","CurriculumName","SubjectCode","Type","RotationSet"])
    if f_courses:
        courses_df = build_courses(f_courses, list(courses_df.columns))
        outputs["COURSES.csv"] = courses_df.to_csv(index=False).encode("utf-8")
        st.success(f"COURSES.csv ✓ ({len(courses_df)} rows)")
        diagnostics.write({"courses_rows": len(courses_df), "course_cols": list(courses_df.columns)})

    # Students + Class Memberships from same uploads
    if f_students:
        student_cols = [
            "StudentCode","FirstName","LastName","CoreStudentBodyCode","YearLevelCode","YearLevel","Curriculum","Gender","Email"
        ]
        students = build_students(f_students, student_cols)
        outputs["Student.csv"] = students.to_csv(index=False).encode("utf-8")
        st.success(f"Student.csv ✓ ({len(students)} rows)")
        diagnostics.write({"students_rows": len(students), "student_cols": list(students.columns)})

        memberships = build_class_memberships(f_students)
        outputs["ClassMemberships.csv"] = memberships.to_csv(index=False).encode("utf-8")
        st.success(f"ClassMemberships.csv ✓ ({len(memberships)} rows)")
        diagnostics.write({"class_membership_rows": len(memberships), "class_membership_cols": list(memberships.columns)})

    # Classes & Lessons (requires courses for rotation lookup)
    if f_classes is not None:
        df_classes = _read_any(f_classes)
        classes_out = build_classes_and_lessons(df_classes, courses_df)
        outputs["ClassesAndLessons.csv"] = classes_out.to_csv(index=False).encode("utf-8")
        st.success(f"ClassesAndLessons.csv ✓ ({len(classes_out)} rows)")
        diagnostics.write({"classes_rows": len(classes_out), "classes_cols": list(classes_out.columns)})

    # Subjects (static include)
    if f_subjects is not None:
        outputs["SUBJECT.csv"] = f_subjects.read()
        st.success("SUBJECT.csv ✓ (included as-is)")
        diagnostics.write({"subjects_bytes": "included"})

    if not outputs:
        st.warning("Please upload at least one source file.")
    else:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in outputs.items():
                zf.writestr(name, data)
        st.download_button(
            "⬇️ Download all as ZIP",
            data=zip_buf.getvalue(),
            file_name="school-data-bundle.zip",
            mime="application/zip",
        )

st.caption("Robust reading + fuzzy matching. If something looks empty, open Diagnostics to see matched columns and row counts.")
