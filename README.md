# School Data Transformer

A single-page Streamlit app for uploading multiple school-related spreadsheets (Rooms, Teachers, Students, Courses, Subjects, and Classes & Lessons) and downloading all processed outputs as one ZIP bundle.

## Quickstart

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Outputs
- ROOM.csv
- Teacher.csv
- Student.csv
- ClassMemberships.csv
- SUBJECT.csv
- COURSES.csv
- ClassesAndLessons.csv

Each generated automatically from your uploads based on Compass-style mappings.
