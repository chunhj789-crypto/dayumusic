# Render.com용 app.py 수정사항

from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

# ============================================
# 1. SECRET_KEY 설정 (환경 변수 사용)
# ============================================
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# ============================================
# 2. 데이터베이스 설정 (중요!)
# ============================================
# Render는 PostgreSQL 사용, 로컬은 SQLite 사용
if os.environ.get('DATABASE_URL'):
    # Render.com 환경 (PostgreSQL)
    database_url = os.environ.get('DATABASE_URL')
    # Render의 PostgreSQL URL 형식 변경 (postgres:// → postgresql://)
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # 로컬 개발 환경 (SQLite)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ============================================
# 3. 파일 업로드 설정
# ============================================
# Render는 임시 파일 시스템 사용 (재배포 시 삭제됨)
# 나중에 Cloudinary 같은 외부 스토리지로 변경 필요
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# 업로드 폴더가 없으면 생성
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# ============================================
# 4. 데이터베이스 모델 (기존과 동일)
# ============================================
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(100), nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    images = db.relationship('Image', backref='post', lazy=True, cascade='all, delete-orphan')

class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    order = db.Column(db.Integer, default=1)
    date_uploaded = db.Column(db.DateTime, default=datetime.utcnow)

# ============================================
# 5. 데이터베이스 초기화 (중요!)
# ============================================
# Render.com에서 자동으로 테이블 생성
with app.app_context():
    db.create_all()

# ============================================
# 6. 관리자 인증 설정
# ============================================
# 환경 변수로 관리자 비밀번호 설정
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')  # 기본값

def check_admin():
    return session.get('is_admin', False)

# ============================================
# 7. 헬퍼 함수들 (기존과 동일)
# ============================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_primary_image(post):
    try:
        image = Image.query.filter_by(post_id=post.id).order_by(Image.order.asc()).first()
        return image
    except:
        return None

def get_image_count(post):
    try:
        count = Image.query.filter_by(post_id=post.id).count()
        return count
    except:
        return 0

def get_display_date(post):
    return post.date_posted

@app.context_processor
def inject_template_vars():
    return {
        'get_image_count': get_image_count,
        'get_primary_image': get_primary_image,
        'get_display_date': get_display_date,
        'is_admin': check_admin()
    }

# ============================================
# 8. 라우트들 (기존과 동일하게 유지)
# ============================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/board')
def board():
    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template('board.html', posts=posts, is_admin=check_admin())

@app.route('/post/<int:post_id>')
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    images = Image.query.filter_by(post_id=post_id).order_by(Image.order.asc()).all()
    return render_template('post.html', post=post, images=images, is_admin=check_admin())

# 관리자 로그인
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['is_admin'] = True
            flash('관리자 로그인 성공!', 'success')
            return redirect(url_for('board'))
        else:
            flash('비밀번호가 틀렸습니다.', 'error')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    flash('로그아웃되었습니다.', 'info')
    return redirect(url_for('index'))

# 글쓰기
@app.route('/write', methods=['GET', 'POST'])
def write_post():
    if not check_admin():
        flash('관리자만 접근할 수 있습니다.', 'error')
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        content = request.form.get('content')
        
        new_post = Post(title=title, author=author, content=content)
        
        try:
            db.session.add(new_post)
            db.session.flush()
            
            # 이미지 처리
            uploaded_files = request.files.getlist('images')
            for i, file in enumerate(uploaded_files):
                if file and file.filename != '' and allowed_file(file.filename):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"{timestamp}_{i+1}_{secure_filename(file.filename)}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    
                    file.save(file_path)
                    
                    new_image = Image(
                        filename=filename,
                        original_filename=file.filename,
                        post_id=new_post.id,
                        order=i + 1
                    )
                    db.session.add(new_image)
            
            db.session.commit()
            flash('게시글이 성공적으로 작성되었습니다!', 'success')
            return redirect(url_for('board'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'게시글 작성 중 오류가 발생했습니다: {str(e)}', 'error')
            return redirect(url_for('write_post'))
    
    return render_template('write.html')

# 글 삭제
@app.route('/post/<int:post_id>/delete', methods=['POST'])
def delete_post(post_id):
    if not check_admin():
        flash('관리자만 접근할 수 있습니다.', 'error')
        return redirect(url_for('admin_login'))
    
    post = Post.query.get_or_404(post_id)
    
    try:
        # 연결된 이미지 파일들 삭제
        images = Image.query.filter_by(post_id=post_id).all()
        for image in images:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # 데이터베이스에서 삭제 (이미지는 cascade로 자동 삭제)
        db.session.delete(post)
        db.session.commit()
        
        flash('게시글이 삭제되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'삭제 중 오류가 발생했습니다: {str(e)}', 'error')
    
    return redirect(url_for('board'))

# ============================================
# 9. 앱 실행 (Render에서는 gunicorn 사용)
# ============================================
if __name__ == '__main__':
    # 로컬 개발용
    app.run(debug=True)
    # Render에서는 gunicorn이 실행하므로 이 부분은 무시됨