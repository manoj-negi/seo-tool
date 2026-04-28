from flask import Flask, render_template, request
import asyncio
from analyzer.seo import analyze_seo

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    url = request.form.get("url")

    result = asyncio.run(analyze_seo(url))  # IMPORTANT FIX

    return render_template("index.html", result=result, url=url)

if __name__ == "__main__":
    app.run(debug=True)