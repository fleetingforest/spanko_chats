from werkzeug.middleware.dispatcher import DispatcherMiddleware
from app import app as main_app
from disciplinarian_site.app import app as disciplinarian_app

# Mount the disciplinarian app under /disciplinarian while keeping the main app at root
app = DispatcherMiddleware(main_app, {
    '/disciplinarian': disciplinarian_app
})
