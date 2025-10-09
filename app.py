from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

# 환경 변수 설정
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# 데이터베이스 설정
if os.environ.get('DATABASE_URL'):
    database_url = os.environ.get('DATABASE_URL')
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 파일 업로드 설정
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 16 * 1024 * 1024

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# ============================================
# 데이터베이스 모델
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

# 데이터베이스 초기화
with app.app_context():
    db.create_all()

# ============================================
# 관리자 설정
# ============================================
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

def check_admin():
    return session.get('is_admin', False)

# ============================================
# 헬퍼 함수
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
# 라우트
# ============================================

# 홈페이지
@app.route('/')
def index():
    return render_template('index.html')

# 인사말
@app.route('/greeting')
def greeting():
    return render_template('greeting.html')

# 멤버 소개
@app.route('/members')
def members():
    return render_template('members.html')

# 힐링콘서트
@app.route('/healingconcert')
def healingconcert():
    return render_template('healingconcert.html')

# 포트폴리오
@app.route('/portfolio')
def portfolio():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 9
        
        # 기본 쿼리
        query = Video.query.order_by(Video.date_uploaded.desc())
        
        # 페이지네이션
        videos_paginated = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        # 각 비디오의 본문에서 날짜 추출하고 +1일 처리
        for video in videos_paginated.items:
            if video.description:
                # 본문에서 YYYY.M.D 또는 YYYY.MM.DD 형식의 날짜 찾기
                date_match = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', video.description)
                if date_match:
                    try:
                        # 찾은 날짜를 파싱하고 +1일 추가
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        day = int(date_match.group(3))
                        
                        original_date = datetime(year, month, day)
                        next_day = original_date + timedelta(days=1)
                        video.display_date = next_day.strftime('%Y-%m-%d')
                    except ValueError:
                        video.display_date = '날짜 없음'
                else:
                    video.display_date = '날짜 없음'
            else:
                video.display_date = '날짜 없음'
        
        return render_template('portfolio.html', videos=videos_paginated.items, pagination=videos_paginated)
        
    except Exception as e:
        print(f"포트폴리오 오류: {e}")
        flash('포트폴리오를 불러오는 중 문제가 발생했습니다.')
        return render_template('portfolio.html', videos=[], pagination=None)
    

# 연락처
@app.route('/contact')
def contact():
    return render_template('contact.html')

# 게시판

# 게시글 상세
@app.route('/post/<int:post_id>')
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    images = Image.query.filter_by(post_id=post_id).order_by(Image.order.asc()).all()
    return render_template('post.html', post=post, images=images, is_admin=check_admin())

# /admin 경로 추가
@app.route('/admin')
def admin():
    # 이미 로그인한 경우 게시판으로
    if check_admin():
        return redirect(url_for('board'))
    # 로그인 안 한 경우 로그인 페이지로
    return redirect(url_for('admin_login'))

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

# 관리자 로그아웃
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
        images = Image.query.filter_by(post_id=post_id).all()
        for image in images:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        db.session.delete(post)
        db.session.commit()
        
        flash('게시글이 삭제되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'삭제 중 오류가 발생했습니다: {str(e)}', 'error')
    
    return redirect(url_for('board'))


# 디버그 라우트 - templates 폴더 확인
@app.route('/debug/templates')
def debug_templates():
    import os
    
    results = {
        'app_root': os.getcwd(),
        'template_folder': app.template_folder,
        'template_folder_absolute': os.path.abspath(app.template_folder),
        'exists': os.path.exists(app.template_folder),
        'files': [],
        'all_files_in_root': []
    }
    
    # templates 폴더 파일 목록
    if os.path.exists(app.template_folder):
        try:
            for root, dirs, files in os.walk(app.template_folder):
                for file in files:
                    filepath = os.path.join(root, file)
                    results['files'].append(filepath)
        except Exception as e:
            results['files_error'] = str(e)
    
    # 현재 디렉토리 구조
    try:
        for item in os.listdir(os.getcwd()):
            item_path = os.path.join(os.getcwd(), item)
            is_dir = os.path.isdir(item_path)
            results['all_files_in_root'].append({
                'name': item,
                'is_directory': is_dir
            })
    except Exception as e:
        results['root_error'] = str(e)
    
    return results

# board 라우트 수정 - 에러 메시지 추가
@app.route('/board')
def board():
    import os
    try:
        posts = Post.query.order_by(Post.date_posted.desc()).all()
        return render_template('board.html', posts=posts, is_admin=check_admin())
    except Exception as e:
        # 상세한 에러 정보 반환
        return f"""
        <h1>Board Error</h1>
        <p>Error: {str(e)}</p>
        <p>Template folder: {app.template_folder}</p>
        <p>Exists: {os.path.exists(app.template_folder)}</p>
        <p>Files in templates: {os.listdir(app.template_folder) if os.path.exists(app.template_folder) else 'Not found'}</p>
        <a href="/debug/templates">Check debug info</a>
        """, 500
# 404 에러 핸들러
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# 500 에러 핸들러
@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True)