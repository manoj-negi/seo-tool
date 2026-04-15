from flask import Flask, render_template, request
from analyzer.seo import analyze_seo

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    url = request.form.get("url")

    if not url:
        return "Please enter URL"

    result = analyze_seo(url)
    return render_template("index.html", result=result, url=url)

if __name__ == "__main__":
    app.run(debug=True)