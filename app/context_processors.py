from flask import g, current_app
from flask_login import current_user
from app.models import Notification, StockRequest

def inject_notifications():
    """Inject notifications into all templates."""
    try:
        if not hasattr(current_user, 'is_authenticated'):
            return {
                'notifications': [],
                'notifications_count': 0,
                'pending_verifications_count': 0
            }
            
        if current_user.is_authenticated and current_user.role == 'agrodealer':
            # Get all notifications for debugging
            all_notifications = Notification.query.filter_by(
                user_id=current_user.id
            ).order_by(Notification.created_at.desc()).all()
            
            # Get unread notifications for display
            unread_notifications = Notification.query.filter_by(
                user_id=current_user.id,
                is_read=False
            ).order_by(Notification.created_at.desc()).limit(5).all()
            
            unread_count = Notification.query.filter_by(
                user_id=current_user.id,
                is_read=False
            ).count()
            
            print(f"Found {len(all_notifications)} total notifications")
            print(f"Found {len(unread_notifications)} unread notifications")
            print(f"Unread count: {unread_count}")
            
            # Get pending verifications count for MD
            pending_verifications_count = 0
            if current_user.role == 'md':
                pending_verifications_count = StockRequest.query.filter_by(
                    status='approved_by_md'
                ).count()
            
            return {
                'notifications': unread_notifications,
                'notifications_count': len(unread_notifications),
                'pending_verifications_count': pending_verifications_count
            }
    except Exception as e:
        current_app.logger.error(f"Error in context processor: {str(e)}")
        
    return {
        'notifications': [],
        'notifications_count': 0,
        'pending_verifications_count': 0
    } 