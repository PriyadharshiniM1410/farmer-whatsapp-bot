from app import create_app

app = create_app()

@app.route('/healthz')
def health_check():
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)