from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_scss import Scss
from flask_cors import CORS
from datetime import datetime
import os

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# MySQL Database Configuration
# Update these settings according to your MySQL setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://username:password@localhost/inventory_db'
# For development, you can also use SQLite as fallback:
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'

# Initialize extensions
db = SQLAlchemy(app)
CORS(app)  # Enable CORS for API endpoints
Scss(app, static_dir='static', asset_dir='assets')

# Database Models
class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('Item', backref='category', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'item_count': len(self.items),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Item(db.Model):
    __tablename__ = 'items'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    price = db.Column(db.DECIMAL(10, 2), nullable=False, default=0.0)
    sku = db.Column(db.String(50), unique=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'quantity': self.quantity,
            'price': float(self.price),
            'sku': self.sku,
            'category': self.category.name if self.category else None,
            'category_id': self.category_id,
            'total_value': float(self.quantity * self.price),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class StockMovement(db.Model):
    __tablename__ = 'stock_movements'
    
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    movement_type = db.Column(db.String(20), nullable=False)  # 'in', 'out', 'adjustment'
    quantity = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    item = db.relationship('Item', backref='stock_movements')

# Routes
@app.route('/')
def index():
    items = Item.query.all()
    categories = Category.query.all()
    total_items = len(items)
    total_value = sum(float(item.quantity * item.price) for item in items)
    low_stock_items = Item.query.filter(Item.quantity < 10).all()
    recent_movements = StockMovement.query.order_by(StockMovement.created_at.desc()).limit(5).all()
    
    return render_template('index.html', 
                         items=items, 
                         categories=categories,
                         total_items=total_items,
                         total_value=total_value,
                         low_stock_items=low_stock_items,
                         recent_movements=recent_movements)

@app.route('/items')
def items():
    page = request.args.get('page', 1, type=int)
    category_id = request.args.get('category', type=int)
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'name')
    
    query = Item.query
    
    if category_id:
        query = query.filter_by(category_id=category_id)
    
    if search:
        query = query.filter(
            db.or_(
                Item.name.contains(search),
                Item.description.contains(search),
                Item.sku.contains(search)
            )
        )
    
    # Sorting
    if sort_by == 'name':
        query = query.order_by(Item.name)
    elif sort_by == 'quantity':
        query = query.order_by(Item.quantity.desc())
    elif sort_by == 'price':
        query = query.order_by(Item.price.desc())
    elif sort_by == 'created':
        query = query.order_by(Item.created_at.desc())
    
    items = query.paginate(page=page, per_page=15, error_out=False)
    categories = Category.query.all()
    
    return render_template('items.html', items=items, categories=categories, 
                         current_category=category_id, search=search, sort_by=sort_by)

@app.route('/add_item', methods=['GET', 'POST'])
def add_item():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        quantity = int(request.form['quantity'])
        price = float(request.form['price'])
        sku = request.form['sku'] if request.form['sku'] else None
        category_id = int(request.form['category_id'])
        
        # Check if SKU already exists
        if sku and Item.query.filter_by(sku=sku).first():
            flash('SKU already exists. Please use a unique SKU.', 'error')
            categories = Category.query.all()
            return render_template('add_item.html', categories=categories)
        
        item = Item(name=name, description=description, quantity=quantity, 
                   price=price, sku=sku, category_id=category_id)
        
        try:
            db.session.add(item)
            db.session.commit()
            
            # Record stock movement
            if quantity > 0:
                movement = StockMovement(
                    item_id=item.id,
                    movement_type='in',
                    quantity=quantity,
                    reason='Initial stock'
                )
                db.session.add(movement)
                db.session.commit()
            
            flash('Item added successfully!', 'success')
            return redirect(url_for('items'))
        except Exception as e:
            flash('Error adding item. Please try again.', 'error')
            db.session.rollback()
    
    categories = Category.query.all()
    return render_template('add_item.html', categories=categories)

@app.route('/edit_item/<int:id>', methods=['GET', 'POST'])
def edit_item(id):
    item = Item.query.get_or_404(id)
    
    if request.method == 'POST':
        old_quantity = item.quantity
        
        item.name = request.form['name']
        item.description = request.form['description']
        item.quantity = int(request.form['quantity'])
        item.price = float(request.form['price'])
        item.category_id = int(request.form['category_id'])
        item.updated_at = datetime.utcnow()
        
        # Handle SKU update
        new_sku = request.form['sku'] if request.form['sku'] else None
        if new_sku != item.sku:
            if new_sku and Item.query.filter(Item.sku == new_sku, Item.id != id).first():
                flash('SKU already exists. Please use a unique SKU.', 'error')
                categories = Category.query.all()
                return render_template('edit_item.html', item=item, categories=categories)
            item.sku = new_sku
        
        try:
            db.session.commit()
            
            # Record stock movement if quantity changed
            if old_quantity != item.quantity:
                movement_type = 'in' if item.quantity > old_quantity else 'out'
                quantity_change = abs(item.quantity - old_quantity)
                movement = StockMovement(
                    item_id=item.id,
                    movement_type=movement_type,
                    quantity=quantity_change,
                    reason='Manual adjustment'
                )
                db.session.add(movement)
                db.session.commit()
            
            flash('Item updated successfully!', 'success')
            return redirect(url_for('items'))
        except Exception as e:
            flash('Error updating item. Please try again.', 'error')
            db.session.rollback()
    
    categories = Category.query.all()
    return render_template('edit_item.html', item=item, categories=categories)

@app.route('/delete_item/<int:id>')
def delete_item(id):
    item = Item.query.get_or_404(id)
    
    try:
        db.session.delete(item)
        db.session.commit()
        flash('Item deleted successfully!', 'success')
    except Exception as e:
        flash('Error deleting item. Please try again.', 'error')
        db.session.rollback()
    
    return redirect(url_for('items'))

@app.route('/categories')
def categories():
    categories = Category.query.all()
    return render_template('categories.html', categories=categories)

@app.route('/add_category', methods=['GET', 'POST'])
def add_category():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        
        category = Category(name=name, description=description)
        
        try:
            db.session.add(category)
            db.session.commit()
            flash('Category added successfully!', 'success')
            return redirect(url_for('categories'))
        except Exception as e:
            flash('Error adding category. Please try again.', 'error')
            db.session.rollback()
    
    return render_template('add_category.html')

@app.route('/stock_movements')
def stock_movements():
    page = request.args.get('page', 1, type=int)
    item_id = request.args.get('item', type=int)
    
    query = StockMovement.query
    
    if item_id:
        query = query.filter_by(item_id=item_id)
    
    movements = query.order_by(StockMovement.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    items = Item.query.all()
    
    return render_template('stock_movements.html', movements=movements, items=items, current_item=item_id)

# API Routes
@app.route('/api/items')
def api_items():
    items = Item.query.all()
    return jsonify([item.to_dict() for item in items])

@app.route('/api/categories')
def api_categories():
    categories = Category.query.all()
    return jsonify([category.to_dict() for category in categories])

@app.route('/api/items/<int:id>')
def api_item(id):
    item = Item.query.get_or_404(id)
    return jsonify(item.to_dict())

@app.route('/api/low_stock')
def api_low_stock():
    threshold = request.args.get('threshold', 10, type=int)
    items = Item.query.filter(Item.quantity < threshold).all()
    return jsonify([item.to_dict() for item in items])

@app.route('/api/stats')
def api_stats():
    items = Item.query.all()
    categories = Category.query.all()
    
    stats = {
        'total_items': len(items),
        'total_categories': len(categories),
        'total_value': sum(float(item.quantity * item.price) for item in items),
        'low_stock_count': len([item for item in items if item.quantity < 10]),
        'out_of_stock_count': len([item for item in items if item.quantity == 0])
    }
    
    return jsonify(stats)

# Initialize database
def init_db():
    """Initialize database with sample data"""
    db.create_all()
    
    # Add sample categories if none exist
    if not Category.query.first():
        categories = [
            Category(name='Electronics', description='Electronic devices and components'),
            Category(name='Office Supplies', description='Office and stationery items'),
            Category(name='Tools', description='Hardware and tools'),
            Category(name='Furniture', description='Office and home furniture'),
            Category(name='Software', description='Software licenses and digital products')
        ]
        
        for category in categories:
            db.session.add(category)
        
        db.session.commit()
        
        # Add sample items
        items = [
            Item(name='Laptop Dell Inspiron 15', description='15-inch laptop with Intel i5 processor', 
                 quantity=5, price=899.99, sku='DELL-INS-15', category_id=1),
            Item(name='Wireless Mouse', description='Logitech wireless optical mouse', 
                 quantity=25, price=29.99, sku='LOG-MOUSE-01', category_id=1),
            Item(name='USB-C Hub', description='7-in-1 USB-C hub with HDMI', 
                 quantity=15, price=49.99, sku='HUB-USBC-01', category_id=1),
            Item(name='Printer Paper A4', description='White paper 500 sheets per pack', 
                 quantity=100, price=8.99, sku='PAPER-A4-500', category_id=2),
            Item(name='Blue Pens Pack', description='Pack of 10 blue ballpoint pens', 
                 quantity=50, price=12.99, sku='PEN-BLUE-10', category_id=2),
            Item(name='Screwdriver Set', description='Phillips and flathead screwdriver set', 
                 quantity=8, price=24.99, sku='TOOL-SCREW-01', category_id=3),
            Item(name='Office Chair', description='Ergonomic office chair with lumbar support', 
                 quantity=3, price=199.99, sku='CHAIR-ERG-01', category_id=4),
            Item(name='Microsoft Office 365', description='Annual subscription license', 
                 quantity=20, price=99.99, sku='MS-OFF-365', category_id=5)
        ]
        
        for item in items:
            db.session.add(item)
            
            # Add initial stock movement
            movement = StockMovement(
                item_id=item.id,
                movement_type='in',
                quantity=item.quantity,
                reason='Initial stock'
            )
            db.session.add(movement)
        
        db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
