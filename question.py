from app import db, Quiz, app

question1 = Quiz(
    question="Apa yang dimaksud dengan Kecerdasan Buatan (AI)?",
    option_a="Sistem yang dapat berpikir dan belajar dari data",
    option_b="Sistem yang dapat menggantikan manusia sepenuhnya",
    option_c="Sistem yang hanya digunakan dalam permainan",
    option_d="Sistem yang memerlukan banyak energi untuk bekerja",
    answer="A"
)

question2 = Quiz(
    question="Pada pengembangan AI, library Python apa yang digunakan untuk pemrosesan gambar?",
    option_a="Pandas",
    option_b="NumPy",
    option_c="Matplotlib",
    option_d="OpenCV",
    answer="D",
)

question3 = Quiz(
    question="Apa yang dimaksud dengan Unsupervised Learning?",
    option_a="Proses belajar dengan pengalaman langsung tanpa data",
    option_b="Proses di mana algoritma belajar dari data yang berlabel",
    option_c="Proses di mana algoritma belajar dari data yang tidak berlabel",
    option_d="Proses di mana algoritma bekerja tanpa model matematika",
    answer="C"
)

question4 = Quiz(
    question="Apakah Deep Learning merupakan bagian dari Machine Learning?",
    option_a="Ya, deep learning adalah subset dari machine learning",
    option_b="Tidak, deep learning adalah topik yang terpisah",
    option_c="Ya, deep learning hanya digunakan untuk video games",
    option_d="Tidak, deep learning adalah bagian dari neural network",
    answer="A"
)


with app.app_context():
    db.session.add_all([question1, question2, question3, question4])
    db.session.commit()
    print("Pertanyaan berhasil ditambahkan!")