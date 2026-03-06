import os
from titapp import create_app


app = create_app()


if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    port = int(os.getenv('PORT', '5000'))
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
