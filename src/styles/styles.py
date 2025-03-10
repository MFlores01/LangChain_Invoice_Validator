CSS_STYLE = """
<style>
body {
    background-color: #f8f8f8;
    margin: 0;
    padding: 0;
    font-family: 'Open Sans', sans-serif;
}

/* Top bar with gradient and rounded corners */
.top-bar {
    background: linear-gradient(90deg, #005f73, #0a9396);
    display: flex;
    align-items: center;
    padding: 15px 20px;
    width: 80%;
    margin: 20px auto;
    border-radius: 15px;
    box-shadow: 0 3px 6px rgba(0,0,0,0.2);
}
.top-bar img {
    height: 50px;
    margin-right: 15px;
}
.top-bar h1 {
    color: #ffffff;
    font-size: 2rem;
    margin: 0;
    font-weight: bold;
}

/* Remove big white background behind file uploader */
.upload-section {
    background-color: transparent !important;
    margin: 0 auto !important;
    padding: 0 !important;
    width: 80% !important;
    box-shadow: none !important;
    border: none !important;
}

/* Elevated card with a blue header */
.card-elevated {
    background-color: #ffffff;
    border-radius: 12px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    margin-bottom: 20px;
    overflow: hidden;
}
.card-header {
    background: #005f73;
    color: #ffffff;
    padding: 10px;
    font-size: 1.2rem;
    font-weight: bold;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}
.card-body {
    padding: 15px;
}

/* Table for extracted line items (no colored header) */
.table-custom {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
    color: #333;
}
.table-custom th {
    background-color: #ffffff; /* no color for header */
    color: #333;
}
.table-custom th, .table-custom td {
    padding: 10px;
    border: 1px solid #dddddd;
    text-align: left;
}

/* CSV Download link styling (white, bold) */
.download-link {
    display: inline-block;
    background: #005f73;
    color: #ffffff;
    font-weight: bold;
    padding: 8px 15px;
    border-radius: 6px;
    text-decoration: none !important;
    margin-top: 15px;
}
.download-link:hover {
    background: #004054;
    text-decoration: none !important;
}
a.download-link,
a.download-link:link,
a.download-link:visited,
a.download-link:hover,
a.download-link:active {
  color: #ffffff !important;
  background: #005f73 !important;
  font-weight: bold !important;
  text-decoration: none !important;
  display: inline-block !important;
  padding: 8px 15px !important;
  border-radius: 6px !important;
  margin-top: 15px !important;
}
a.download-link:hover {
  background: #004054 !important;
}

</style>
"""
