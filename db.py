from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

# Association tables for many-to-many relationships
course_students_table = db.Table(
    "course_students",
    db.Model.metadata,
    db.Column("course_id", db.Integer, db.ForeignKey("courses.id")),
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"))
)
 

class User(db.Model):
    """
    User model
    Has many-to-many relationships with Course model (as both student and instructor)
    """
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String, nullable=False)
    netid = db.Column(db.String, nullable=False)
    availiblity = db.Column(db.String, nullable=True)
    eviroment_preference = db.Column(db.String, nullable=True)
    location_preference = db.Column(db.String, nullable=True)
    objective_preference = db.Column(db.String, nullable=True)
    password = db.Column(db.String(256), nullable=False)
    student_courses = db.relationship("Course", secondary=course_students_table, back_populates="students")

    def __init__(self, **kwargs):
        """Initialize a User object"""
        self.name = kwargs.get("name", "")
        self.netid = kwargs.get("netid", "")

    def simple_serialize(self):
        """Serialize a User object without courses"""
        return {
            "id": self.id,
            "name": self.name,
            "netid": self.netid
        }

    def serialize(self):
        """Serialize a User object with courses"""
        return {
            "id": self.id,
            "name": self.name,
            "netid": self.netid,
            "courses": [c.simple_serialize() for c in self.student_courses] + [c.simple_serialize() for c in self.instructor_courses]
        }

class Course(db.Model):
    """
    Course model
    Has many-to-many relationships with User model (for both students and instructors)
    Has one-to-many relationship with Assignment model
    """
    __tablename__ = "courses"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    code = db.Column(db.String, nullable=False)
    name = db.Column(db.String, nullable=False)
    students = db.relationship("User", secondary=course_students_table, back_populates="student_courses")

    def __init__(self, **kwargs):
        """Initialize a Course object"""
        self.code = kwargs.get("code", "")
        self.name = kwargs.get("name", "")

    def serialize(self):
        """Serialize a Course object"""
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "students": [s.simple_serialize() for s in self.students],
        }
    def simple_serialize(self):
        """Serialize a Course object without relationships"""
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name
        }


    
