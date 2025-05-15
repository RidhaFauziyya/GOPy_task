from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'  
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    score = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<User {self.username}>'
    
    quizzes = db.relationship('Quiz', backref='user', lazy=True)

class Quiz(db.Model):
    __tablename__ = 'quizzes'
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(255), nullable=False)
    option_a = db.Column(db.String(100), nullable=False)
    option_b = db.Column(db.String(100), nullable=False)
    option_c = db.Column(db.String(100), nullable=False)
    option_d = db.Column(db.String(100), nullable=False)
    answer = db.Column(db.String(1), nullable=False) 

    def __repr__(self):
        return f'<Quiz {self.id}: {self.question}>'

    user_id = db.Column(db.Integer, ForeignKey('users.id'), nullable=True)