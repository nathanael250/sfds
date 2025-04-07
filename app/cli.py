import click
from flask.cli import with_appcontext
from app.models import User
from app import db
from sqlalchemy import text

@click.command('create-user')
@click.argument('username')
@click.argument('email')
@click.argument('password')
@click.argument('role')
@with_appcontext
def create_user_command(username, email, password, role):
    """Create a new user."""
    user = User(username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.echo(f'Created user {username} with role {role}')

def register_commands(app):
    """Register custom Flask CLI commands."""
    
    @app.cli.command('fix-db')
    @with_appcontext
    def fix_db():
        """Fix database issues."""
        try:
            # Remove quantity field from product table
            db.session.execute(text('ALTER TABLE product DROP COLUMN quantity'))
            db.session.commit()
            click.echo('Successfully removed quantity field from Product table')
        except Exception as e:
            db.session.rollback()
            click.echo(f'Error removing quantity field: {str(e)}') 