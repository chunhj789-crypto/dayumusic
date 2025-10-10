from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

# 환경 변수
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# 데이터베이스 설정
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    print(f"Using PostgreSQL: {DATABASE_URL[:30]}...")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
    print("Using SQLite for local development")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

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
    try:
        db.create_all()
        print("Database tables created successfully!")
    except Exception as e:
        print(f"Error creating database tables: {e}")

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
        return Image.query.filter_by(post_id=post.id).order_by(Image.order.asc()).first()
    except:
        return None

def get_image_count(post):
    try:
        return Image.query.filter_by(post_id=post.id).count()
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
# 기본 페이지 라우트
# ============================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/greeting')
def greeting():
    return render_template('greeting.html')

@app.route('/members')
def members():
    return render_template('members.html')

@app.route('/healingconcert')
def healingconcert():
    return render_template('healingconcert.html')

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
    


@app.route('/portfolio/search')
def search_videos():
    """영상 검색 API"""
    query = request.args.get('q', '').strip()
    platform = request.args.get('platform', '')
    page = request.args.get('page', 1, type=int)
    
    if not query and not platform:
        return redirect(url_for('portfolio'))
    
    # 검색 쿼리 구성
    video_query = Video.query
    
    if query:
        search_filter = db.or_(
            Video.title.contains(query),
            Video.description.contains(query),
            Video.author.contains(query),
            Video.tags.contains(query)
        )
        video_query = video_query.filter(search_filter)
    
    if platform:
        video_query = video_query.filter(Video.platform == platform)
    
    videos = video_query.order_by(Video.date_uploaded.desc()).paginate(
        page=page, per_page=9, error_out=False
    )
    
    return render_template('portfolio.html', 
                         videos=videos.items, 
                         pagination=videos,
                         search_query=query,
                         search_platform=platform)

@app.route('/portfolio/featured')
def featured_videos():
    """추천 영상 목록"""
    page = request.args.get('page', 1, type=int)
    videos = Video.query.filter_by(is_featured=True).order_by(
        Video.date_uploaded.desc()
    ).paginate(page=page, per_page=9, error_out=False)
    
    return render_template('portfolio.html', 
                         videos=videos.items, 
                         pagination=videos,
                         page_title="추천 영상")

@app.route('/contact')
def contact():
    return render_template('contact.html')

# ============================================
# 게시판 라우트
# ============================================

@app.route('/board')
def board():
    try:
        posts = Post.query.order_by(Post.date_posted.desc()).all()
        return render_template('board.html', posts=posts, is_admin=check_admin())
    except Exception as e:
        print(f"Board error: {e}")
        return f"게시판 로딩 오류: {str(e)}", 500

@app.route('/post/<int:post_id>')
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    images = Image.query.filter_by(post_id=post_id).order_by(Image.order.asc()).all()
    return render_template('post.html', post=post, images=images, is_admin=check_admin())

# ============================================
# 관리자 라우트
# ============================================

@app.route('/admin')
def admin():
    # 이미 로그인한 경우 게시판으로
    if check_admin():
        return redirect(url_for('board'))
    # 로그인 안 한 경우 로그인 페이지로
    return redirect(url_for('admin_login'))

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

# ============================================
# 게시글 작성/수정/삭제
# ============================================

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

# ============================================
# 에러 핸들러
# ============================================

@app.errorhandler(404)
def page_not_found(e):
    try:
        return render_template('404.html'), 404
    except:
        # 404.html이 없는 경우 기본 메시지
        return '''
        <div style="text-align: center; padding: 100px 20px; font-family: Arial, sans-serif;">
            <h1 style="font-size: 5em; color: #8b7355; margin: 0;">404</h1>
            <p style="font-size: 1.2em; color: #666;">페이지를 찾을 수 없습니다.</p>
            <a href="/" style="color: #8b7355; text-decoration: none; font-size: 1.1em;">홈으로 돌아가기</a>
        </div>
        ''', 404

@app.errorhandler(500)
def internal_server_error(e):
    try:
        return render_template('500.html'), 500
    except:
        # 500.html이 없는 경우 기본 메시지
        return '''
        <div style="text-align: center; padding: 100px 20px; font-family: Arial, sans-serif;">
            <h1 style="font-size: 5em; color: #dc3545; margin: 0;">500</h1>
            <p style="font-size: 1.2em; color: #666;">서버 오류가 발생했습니다.</p>
            <a href="/" style="color: #8b7355; text-decoration: none; font-size: 1.1em;">홈으로 돌아가기</a>
        </div>
        ''', 500

# ============================================
# 디버그 라우트 (개발/테스트용)
# ============================================

@app.route('/debug/routes')
def debug_routes():
    """모든 등록된 라우트 확인"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'path': str(rule)
        })
    return {'routes': routes}

@app.route('/debug/templates')
def debug_templates():
    """템플릿 폴더 파일 확인"""
    results = {
        'template_folder': app.template_folder,
        'template_folder_absolute': os.path.abspath(app.template_folder),
        'exists': os.path.exists(app.template_folder),
        'files': []
    }
    
    if os.path.exists(app.template_folder):
        try:
            for root, dirs, files in os.walk(app.template_folder):
                for file in files:
                    filepath = os.path.join(root, file)
                    results['files'].append(filepath)
        except Exception as e:
            results['files_error'] = str(e)
    
    return results

@app.route('/debug/db')
def debug_db():
    """데이터베이스 연결 확인"""
    try:
        db.session.execute(db.text('SELECT 1'))
        posts_count = Post.query.count()
        images_count = Image.query.count()
        
        return {
            'status': 'success',
            'database': 'connected',
            'posts_count': posts_count,
            'images_count': images_count
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }

# ============================================
# 앱 실행
# ============================================

if __name__ == '__main__':
    app.run(debug=True)