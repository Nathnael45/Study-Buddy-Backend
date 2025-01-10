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
    User model d
    """
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String, nullable=False)
    netid = db.Column(db.String, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    availability = db.Column(db.String, nullable=True)
    
    # Set default=False for all preference columns
    location_north = db.Column(db.Boolean, nullable=False, default=False)
    location_south = db.Column(db.Boolean, nullable=False, default=False)
    location_central = db.Column(db.Boolean, nullable=False, default=False)
    location_west = db.Column(db.Boolean, nullable=False, default=False)
    time_morning = db.Column(db.Boolean, nullable=False, default=False)
    time_afternoon = db.Column(db.Boolean, nullable=False, default=False)
    time_evening = db.Column(db.Boolean, nullable=False, default=False)
    objective_study = db.Column(db.Boolean, nullable=False, default=False)
    objective_homework = db.Column(db.Boolean, nullable=False, default=False)
    
    student_courses = db.relationship("Course", secondary=course_students_table, back_populates="students")

    def __init__(self, **kwargs):
        """Initialize a User object"""
        self.name = kwargs.get('name', "")
        self.netid = kwargs.get('netid', "")
        self.password = kwargs.get('password', "")
        
    

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
            "availability": self.availability
        }
    
    def serialize_with_preferences(self):
        """Serialize a User object with preferences"""
        return {
            "id": self.id,
            "name": self.name,
            "netid": self.netid,
            "availability": self.availability,
            "preferences": self.preferences
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


    
