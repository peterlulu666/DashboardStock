import os  
import pandas as pd  
import yfinance as yf  
import dash  
from dash import dcc, html  
from dash.dependencies import Input, Output  
import plotly.express as px  
import io  
import base64  

# Initialize Dash app  
app = dash.Dash(__name__)  

# Layout of the app  
app.layout = html.Div([  
    html.H1("Cumulative Change Dashboard"),  
    
    dcc.Upload(  
        id='upload-data',  
        children=html.Button('Upload Stock List CSV'),  
        multiple=False  
    ),  
    
    dcc.Dropdown(  
        id='cutoff-date-dropdown',  
        options=[],  
        value=None,  
        clearable=False  
    ),  

    dcc.Dropdown(  
        id='name-dropdown',  
        options=[],  
        value=[],  
        multi=True,  
        clearable=False  
    ),  

    dcc.Graph(id='line-plot')  
])  

# Callback to handle file upload  
@app.callback(  
    Output('cutoff-date-dropdown', 'options'),  
    Output('name-dropdown', 'options'),  
    Output('line-plot', 'figure'),  
    Input('upload-data', 'contents')  
)  
def update_output(contents):  
    if contents is None:  
        return [], [], {}  

    # Decode the uploaded file  
    content_type, content_string = contents.split(',')  
    decoded = base64.b64decode(content_string)  
    df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))  

    # Process the uploaded DataFrame  
    stock_list = df['Stock'].tolist()  
    
    # Define the start and end dates  
    start_date = "2025-01-14"  
    end_date = "2025-02-22"  

    # Create a folder for saving files if it doesn't exist  
    output_folder = r"./Stock_Download"  
    os.makedirs(output_folder, exist_ok=True)  

    all_dataframes = []  

    # Loop through each stock symbol and download the data  
    for stock in stock_list:  
        print(f"Downloading data for {stock}...")  

        # Fetch stock data  
        data = yf.download(stock, start=start_date, end=end_date)  

        # Check if data is empty  
        if data.empty:  
            print(f"No data found for {stock}. Skipping...")  
            continue  

        # Reset index, ensuring 'Date' is properly set  
        data.reset_index(inplace=True)  

        # Flatten MultiIndex if present and strip stock name from column headers  
        if isinstance(data.columns, pd.MultiIndex):  
            data.columns = [' '.join(col).strip() for col in data.columns]  

        # Remove the stock name from column headers if it exists  
        data.columns = [col.split(' ')[0] for col in data.columns]  

        # Add a new column for the stock name  
        data['Name'] = stock  

        # Save the data to a CSV file  
        file_path = os.path.join(output_folder, f"{stock}_historical_data.csv")  
        data.to_csv(file_path, index=False, header=True)  

        # Append the DataFrame to the list  
        all_dataframes.append(data)  

    # Concatenate all DataFrames into a single DataFrame  
    combined_df = pd.concat(all_dataframes, ignore_index=True)  

    # Create a copy to avoid modifying the original DataFrame  
    combined_df_with_change = combined_df.copy()  

    # Initialize 'Change' column with NaN  
    combined_df_with_change['Change'] = pd.NA  

    # Group by 'Name'  
    grouped = combined_df_with_change.groupby('Name')  

    # Iterate through each group  
    for name, group in grouped:  
        # Calculate 'Change' within each group  
        for i in range(1, len(group)):  
            combined_df_with_change.loc[group.index[i], 'Change'] = (group['Close'].iloc[i] - group['Close'].iloc[i-1]) / group['Close'].iloc[i-1]  

    # Get unique dates from the DataFrame  
    unique_dates = sorted(combined_df_with_change['Date'].unique())  

    # Create a DataFrame for the unique date range  
    date_df = pd.DataFrame({'Cutoff_Date': unique_dates})  

    # Cross join with the combined DataFrame  
    combined_df_with_cutoff = combined_df_with_change.merge(date_df, how='cross')  

    # Sort the DataFrame  
    combined_df_with_cutoff = combined_df_with_cutoff.sort_values(by=['Cutoff_Date', 'Name', 'Date'], ascending=[True, True, True])  

    # Move 'Cutoff_Date' to the first column  
    cols = list(combined_df_with_cutoff.columns)  
    cols.insert(0, cols.pop(cols.index('Cutoff_Date')))  
    combined_df_with_cutoff = combined_df_with_cutoff[cols]  

    # Convert 'Date' and 'Cutoff_Date' columns to datetime objects if they aren't already  
    combined_df_with_cutoff['Date'] = pd.to_datetime(combined_df_with_cutoff['Date'])  
    combined_df_with_cutoff['Cutoff_Date'] = pd.to_datetime(combined_df_with_cutoff['Cutoff_Date'])  

    # Apply the logic to create the adjusted 'Change' column  
    combined_df_with_cutoff['Adjusted_Change'] = combined_df_with_cutoff.apply(lambda row: 0 if row['Date'] <= row['Cutoff_Date'] else row['Change'], axis=1)  

    # Calculate cumulative sum of 'Adjusted_Change', resetting for each new 'Name' column  
    combined_df_with_cutoff['Cumulative_Change'] = combined_df_with_cutoff.groupby(['Name', 'Cutoff_Date'])['Adjusted_Change'].cumsum()  

    # Filter the DataFrame  
    filtered_df = combined_df_with_cutoff[combined_df_with_cutoff['Date'] >= combined_df_with_cutoff['Cutoff_Date']]  

    # Keep only the desired columns  
    filtered_df = filtered_df[['Cutoff_Date', 'Date', 'Name', 'Cumulative_Change']]  

    # Update dropdown options  
    cutoff_options = [{'label': date, 'value': date} for date in filtered_df['Cutoff_Date'].unique()]  
    name_options = [{'label': name, 'value': name} for name in filtered_df['Name'].unique()]  

    # Create the figure  
    fig = px.line(filtered_df, x='Date', y='Cumulative_Change', color='Name', title='Cumulative Change')  

    # Add the horizontal line at y = 0  
    fig.add_hline(y=0, line_dash="dash", line_color="gray")  

    return cutoff_options, name_options, fig  

# Run the app  
if __name__ == "__main__":  
    app.run_server(host='0.0.0.0', port=int(os.environ.get("PORT", 8050)))
