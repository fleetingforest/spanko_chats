"""
This module provides functions for creating and displaying Patreon promotions
based on token usage thresholds.
"""

def check_token_thresholds(ip_address, get_tokens, db, session, is_authenticated, get_user_patreon_status):
    """
    Check if user has hit specific token thresholds and return appropriate Patreon promotion message.
    Returns a dictionary with promotion details instead of HTML.
    """
    # First check if the user is logged in and is already a Patreon subscriber
    user_email = session.get('user_email')
    if user_email and is_authenticated():
        patreon_status = get_user_patreon_status(user_email)
        if patreon_status == "active":
            # Don't show promotions to active Patreon subscribers
            return None
    # If not logged in or not a Patreon subscriber, proceed to check thresholds
            
    tokens = get_tokens(ip_address)
    
    # Get shown notification thresholds for this user
    doc_ref = db.collection('token_notifications').document(ip_address)
    doc = doc_ref.get()
    shown_thresholds = doc.to_dict().get('shown_thresholds', []) if doc.exists else []
    
    # Check each threshold and only show notifications for new thresholds
    notification = None
    
    # First threshold: 50,000 tokens
    if tokens >= 50000 and 50000 not in shown_thresholds:
        notification = {
            "title": "Enjoying Spanking Chat?",
            "message": "Support us on Patreon!",
            "button_text": "Join Patreon!",
            "threshold": 50000
        }
        shown_thresholds.append(50000)
    
    # Second threshold: 250,000 tokens
    elif tokens >= 250000 and 250000 not in shown_thresholds:
        notification = {
            "title": "Enjoying Spanking Chat?",
            "message": "Support us on Patreon!",
            "button_text": "Support Us on Patreon!",
            "threshold": 250000
        }
        shown_thresholds.append(250000)
    
    # Recurring thresholds: every 250k after 500k
    elif tokens >= 500000:
        # Calculate the nearest 250k milestone
        milestone = 500000 + (((tokens - 500000) // 250000) * 250000)
        if milestone not in shown_thresholds and tokens >= milestone:
            notification = {
                "title": "You're amazing!",
                "message": "Your ongoing usage helps us improve. Patreon members get priority support!",
                "button_text": "Become a Patron!",
                "threshold": milestone
            }
            shown_thresholds.append(milestone)
    
    # Update the database with the new shown thresholds if we're showing a notification
    if notification:
        doc_ref.set({'shown_thresholds': shown_thresholds}, merge=True)
    
    return notification
