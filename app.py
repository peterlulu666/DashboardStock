import dash
from dash import dcc, html, Dash
from dash.dependencies import Input, Output, State
import pandas as pd
import yfinance as yf
import plotly.express as px
import base64
import io
from datetime import datetime, timedelta

# Initialize Dash app
app = Dash(__name__)
server = app.server  # For Vercel

app.layout = html.Div([
    html.H1("Stock Data Dashboard"),

    # File Upload Component
    html.Label("Upload stock_list.csv:"),
    dcc.Upload(
        id='upload-data',
        children=html.Button('Upload File'),
        accept='.csv',
        multiple=False
    ),

    # Date Range Picker for Start and End Dates
    html.Label("Select Date Range for Data Download:"),
    dcc.DatePickerRange(
        id='date-picker-range',
        min_date_allowed=(datetime.today() - timedelta(days=5 * 365)).date(),  # 5 years back
        max_date_allowed=(datetime.today() + timedelta(days=365)).date(),  # 1 year into future
        initial_visible_month=datetime.today().date(),
        start_date=(datetime.today() - timedelta(days=30)).date(),  # Default: last 30 days
        end_date=datetime.today().date()
    ),

    # Cutoff Date Dropdown
    html.Label("Select Cutoff Date:"),
    dcc.Dropdown(
        id='cutoff-date-dropdown',
        options=[],
        clearable=False
    ),

    # Stock Names Dropdown
    html.Label("Select Stocks:"),
    dcc.Dropdown(
        id='name-dropdown',
        options=[],
        multi=True,
        clearable=False
    ),

    # Loading Indicator
    dcc.Loading(
        id="loading",
        type="default",
        children=dcc.Graph(id='line-plot')
    ),

    # Status Messages
    html.Div(id='output-message', style={'margin-top': '20px'}),
    html.Div(id='processing-status', style={'color': 'blue', 'margin-top': '10px'})
])

# Parse uploaded CSV content
def parse_csv(contents, filename):
    if contents is None or not filename.endswith('.csv'):
        return None, "Please upload a valid CSV file."
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    try:
        df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
        if 'Stock' not in df.columns:
            return None, "CSV must contain a 'Stock' column."
        return df, f"Uploaded {filename} successfully."
    except Exception as e:
        return None, f"Error parsing CSV: {str(e)}"

# Download stock data with error tracking
def download_stock_data(stock_list, start_date, end_date):
    all_data = []
    errors = []
    for stock in stock_list:
        try:
            data = yf.download(stock, start=start_date, end=end_date)
            if data.empty:
                errors.append(f"{stock}: No data available")
                continue
            data = data.reset_index()
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [' '.join(col).strip() for col in data.columns]
            data.columns = [col.split(' ')[0] for col in data.columns]
            data['Name'] = stock
            all_data.append(data[['Date', 'Close', 'Name']])
        except Exception as e:
            errors.append(f"{stock}: Error - {str(e)}")
    if not all_data:
        return None, errors if errors else ["No valid data for any stock"]
    return pd.concat(all_data, ignore_index=True), errors

# Calculate cumulative change with cutoff
def calculate_cumulative_change(df, cutoff_date):
    df = df.copy()
    df['Date'] = pd.to_datetime(df['Date'])
    df['Change'] = df.groupby('Name')['Close'].pct_change()
    df['Adjusted_Change'] = df.apply(
        lambda row: 0 if row['Date'] <= pd.to_datetime(cutoff_date) else row['Change'], axis=1
    )
    df['Cumulative_Change'] = df.groupby('Name')['Adjusted_Change'].cumsum().fillna(0)
    return df[['Date', 'Name', 'Cumulative_Change']]

# Update options after upload and date selection
@app.callback(
    [Output('name-dropdown', 'options'),
     Output('name-dropdown', 'value'),
     Output('cutoff-date-dropdown', 'options'),
     Output('cutoff-date-dropdown', 'value'),
     Output('output-message', 'children')],
    [Input('upload-data', 'contents'),
     Input('upload-data', 'filename'),
     Input('date-picker-range', 'start_date'),
     Input('date-picker-range', 'end_date')]
)
def update_options(contents, filename, start_date, end_date):
    if contents is None or start_date is None or end_date is None:
        return [], [], [], None, "Upload a CSV and select dates to proceed."

    stock_df, message = parse_csv(contents, filename)
    if stock_df is None:
        return [], [], [], None, message

    stock_list = stock_df['Stock'].tolist()
    df, errors = download_stock_data(stock_list, start_date, end_date)
    if df is None:
        return [], [], [], None, f"{message} Errors: {', '.join(errors)}"

    # Stock options
    stock_options = [{'label': stock, 'value': stock} for stock in stock_list]
    default_stocks = stock_list[:1]

    # Cutoff date options
    df['Date'] = pd.to_datetime(df['Date'])
    cutoff_options = [{'label': date.strftime('%Y-%m-%d'), 'value': date.strftime('%Y-%m-%d')} 
                      for date in sorted(df['Date'].unique())]
    default_cutoff = cutoff_options[0]['value'] if cutoff_options else None

    error_msg = f" Errors: {', '.join(errors)}" if errors else ""
    return stock_options, default_stocks, cutoff_options, default_cutoff, f"{message}{error_msg}"

# Update graph with loading status
@app.callback(
    [Output('line-plot', 'figure'),
     Output('processing-status', 'children')],
    [Input('upload-data', 'contents'),
     Input('upload-data', 'filename'),
     Input('date-picker-range', 'start_date'),
     Input('date-picker-range', 'end_date'),
     Input('cutoff-date-dropdown', 'value'),
     Input('name-dropdown', 'value')]
)
def update_graph(contents, filename, start_date, end_date, cutoff_date, selected_names):
    if (contents is None or start_date is None or end_date is None or 
        cutoff_date is None or not selected_names):
        return px.line(title="Upload a CSV, select dates, cutoff, and stocks"), ""

    status = "Processing data, please wait..."
    
    stock_df, message = parse_csv(contents, filename)
    if stock_df is None:
        return px.line(title=message), ""

    stock_list = stock_df['Stock'].tolist()
    valid_names = [name for name in selected_names if name in stock_list]

    if not valid_names:
        return px.line(title="No valid stocks selected"), ""

    # Download stock data
    df, errors = download_stock_data(valid_names, start_date, end_date)
    if df is None:
        return px.line(title=f"No data available. Errors: {', '.join(errors)}"), ""

    # Calculate cumulative change
    processed_df = calculate_cumulative_change(df, cutoff_date)

    # Plot
    fig = px.line(
        processed_df,
        x='Date',
        y='Cumulative_Change',
        color='Name',
        title=f"Cumulative Change for {', '.join(valid_names)} (Cutoff: {cutoff_date})",
        labels={"Date": "Date", "Cumulative_Change": "Cumulative Change", "Name": "Stock"}
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray")

    error_msg = f" Errors: {', '.join(errors)}" if errors else ""
    return fig, f"Data loaded successfully.{error_msg}"

if __name__ == "__main__":
    app.run_server(debug=True, port=8050)