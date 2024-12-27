from flask import Flask, request, jsonify
import boto3
from flask_cors import CORS
import datetime
import numpy as np
from sklearn.linear_model import LinearRegression

app = Flask(__name__)
CORS(app)  # Allow CORS for frontend-backend communication
# Create a user and grant permissions for 
#AWSCostAndUsageReportAutomationPolicy

#AWSSupportAccess
#CloudWatchFullAccess
#CloudWatchFullAccessV2
#CostExplorerAccessPolicy
#CostOptimizationHubAdminAccess
#CostOptimizationHubReadOnlyAccess
#Test give policy.json policy


# AWS Configuration
AWS_ACCESS_KEY_ID = '' #Replace
AWS_SECRET_ACCESS_KEY = '' #Replace 
AWS_REGION = 'us-east-1'
SNS_TOPIC_ARN = ''  # Replace with your SNS Topic ARN

# Initialize AWS clients
cloudwatch = boto3.client(
    'cloudwatch',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

sns = boto3.client(
    'sns',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

# In-memory store for alerts (use a database in production)
alerts = []


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "OK"}), 200


@app.route('/alerts/create', methods=['POST'])
def create_alert():
    """Create a billing alert."""
    try:
        # Get the request data
        data = request.json
        if not data or 'threshold' not in data:
            return jsonify({"error": "Invalid payload. 'threshold' is required."}), 400

        threshold = data['threshold']

        # Create a CloudWatch alarm
        alarm_name = f"BillingThresholdAlarm_{threshold}"
        cloudwatch.put_metric_alarm(
            AlarmName=alarm_name,
            MetricName='EstimatedCharges',
            Namespace='AWS/Billing',
            Statistic='Maximum',
            Period=3600,
            EvaluationPeriods=1,
            Threshold=threshold,
            ComparisonOperator='GreaterThanOrEqualToThreshold',
            ActionsEnabled=True,
            AlarmActions=[SNS_TOPIC_ARN],
            Unit='None'
        )

        # Add the alarm to the in-memory store
        alerts.append({"AlarmName": alarm_name, "Threshold": threshold})

        # Send an SNS notification
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject='Billing Alert Created',
            Message=f'A billing alert has been created with a threshold of ${threshold}.'
        )

        return jsonify({"message": "Alert created successfully!"}), 200

    except Exception as e:
        print(f"Error creating alert: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/alerts', methods=['GET'])
def get_alerts():
    """Retrieve all billing alerts."""
    try:
        return jsonify(alerts), 200
    except Exception as e:
        print(f"Error fetching alerts: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/alerts/<string:alarm_name>', methods=['DELETE'])
def delete_alert(alarm_name):
    """Delete a specific billing alert."""
    global alerts
    try:
        # Remove the alert from the in-memory store
        alerts = [alert for alert in alerts if alert["AlarmName"] != alarm_name]

        # Delete the alarm from CloudWatch
        cloudwatch.delete_alarms(
            AlarmNames=[alarm_name]
        )

        return jsonify({"message": f"Alert '{alarm_name}' deleted successfully!"}), 200
    except Exception as e:
        print(f"Error deleting alert: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/suggestions', methods=['GET'])
def get_suggestions():
    """Provide billing data and Trusted Advisor message."""
    try:
        # Initialize AWS Cost Explorer client
        ce = boto3.client(
            'ce',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )

        # Query cost data for the last 30 days
        billing_data = ce.get_cost_and_usage(
            TimePeriod={
                'Start': '2024-10-01',  # Replace with dynamic date logic if needed
                'End': '2024-11-01'
            },
            Granularity='MONTHLY',
            Metrics=['BlendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
        )

        billing_suggestions = []
        for group in billing_data['ResultsByTime'][0]['Groups']:
            service_name = group['Keys'][0]
            cost = float(group['Metrics']['BlendedCost']['Amount'])
            if cost > 0:
                billing_suggestions.append({
                    "Service": service_name,
                    "Cost": f"${cost:.2f}",
                    "Suggestion": f"Review usage of {service_name} for potential cost optimization."
                })

        # Return combined response
        return jsonify({
            "billingSuggestions": billing_suggestions,
            "trustedAdvisorMessage": "AWS Trusted Advisor requires a Premium Support Plan. Please upgrade your account to access Trusted Advisor suggestions."
        }), 200

    except Exception as e:
        print(f"Error fetching suggestions: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/suggestions/billing', methods=['GET'])
def get_billing_data():
    """Fetch AWS cost usage by service."""
    try:
        ce = boto3.client(
            'ce',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )

        # Query cost data for the last 30 days
        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': '2024-10-01',
                'End': '2024-11-01'
            },
            Granularity='MONTHLY',
            Metrics=['BlendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
        )

        suggestions = []
        for group in response['ResultsByTime'][0]['Groups']:
            service_name = group['Keys'][0]
            cost = float(group['Metrics']['BlendedCost']['Amount'])
            if cost > 0:
                suggestions.append({
                    "Service": service_name,
                    "Cost": f"${cost:.2f}",
                    "Suggestion": f"Review usage of {service_name} for optimization."
                })

        return jsonify(suggestions), 200

    except Exception as e:
        print(f"Error fetching billing data: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/forecast', methods=['GET'])
def get_cost_forecast():
    """Generate a cost forecast based on historical AWS cost data."""
    try:
        # Initialize AWS Cost Explorer client
        ce = boto3.client(
            'ce',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )

        # Fetch cost data for the last 6 months
        today = datetime.date.today()
        start_date = (today - datetime.timedelta(days=180)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='MONTHLY',
            Metrics=['BlendedCost'],  # Use 'BlendedCost' or 'UnblendedCost'
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
        )

        # Debug response
      #  print("Cost Explorer Response:", response)

        # Process the historical data
        historical_costs = []
        for result in response['ResultsByTime']:
            # Attempt to fetch from Total -> BlendedCost first
            total_cost = result.get('Total', {}).get('BlendedCost', {}).get('Amount', None)
            if total_cost is not None:
                historical_costs.append(float(total_cost))
            else:
                # If Total is not available, aggregate costs from Groups
                group_costs = sum(
                    float(group['Metrics']['BlendedCost']['Amount'])
                    for group in result.get('Groups', [])
                    if 'BlendedCost' in group['Metrics']
                )
                historical_costs.append(group_costs)

        # Prepare data for linear regression (forecasting)
        X = np.array(range(len(historical_costs))).reshape(-1, 1)  # Time steps
        y = np.array(historical_costs)  # Costs

        model = LinearRegression()
        model.fit(X, y)

        # Predict future costs for the next 3 months
        future_time_steps = np.array(range(len(historical_costs), len(historical_costs) + 3)).reshape(-1, 1)
        predictions = model.predict(future_time_steps)

        forecast = {
            "historical": historical_costs,
            "forecast": predictions.tolist(),
            "months": [(today + datetime.timedelta(days=30 * i)).strftime('%B %Y') for i in range(1, 4)]
        }

        return jsonify(forecast), 200

    except Exception as e:
        print(f"Error fetching cost forecast: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/dashboard-data', methods=['GET'])    
def get_dashboard_data():
    """Aggregate data for the dashboard."""
    try:
        # Initialize AWS Cost Explorer client
        ce = boto3.client(
            'ce',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )

        today = datetime.date.today()
        start_date = (today - datetime.timedelta(days=180)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

        # Fetch historical cost data
        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='MONTHLY',
            Metrics=['BlendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
        )

        # Process data
        historical_data = []
        cost_breakdown = {}
        for result in response['ResultsByTime']:
            time_period = result['TimePeriod']
            period_label = f"{time_period['Start']} - {time_period['End']}"
            
            # Historical total cost
            total_cost = result.get('Total', {}).get('BlendedCost', {}).get('Amount', 0)
            historical_data.append({
                "period": period_label,
                "total_cost": float(total_cost)
            })

            # Cost breakdown by service
            for group in result.get('Groups', []):
                service = group['Keys'][0]
                cost = float(group['Metrics']['BlendedCost']['Amount'])
                if service not in cost_breakdown:
                    cost_breakdown[service] = 0
                cost_breakdown[service] += cost

        # Prepare forecasted data
        X = np.array(range(len(historical_data))).reshape(-1, 1)
        y = np.array([data['total_cost'] for data in historical_data])

        model = LinearRegression()
        model.fit(X, y)

        future_time_steps = np.array(range(len(historical_data), len(historical_data) + 3)).reshape(-1, 1)
        predictions = model.predict(future_time_steps)

        forecast_data = [
            {"month": (today + datetime.timedelta(days=30 * i)).strftime('%B %Y'), "forecasted_cost": float(pred)}
            for i, pred in enumerate(predictions)
        ]

        return jsonify({
            "historical": historical_data,
            "cost_breakdown": cost_breakdown,
            "forecast": forecast_data
        }), 200

    except Exception as e:
        print(f"Error fetching dashboard data: {e}")
        return jsonify({"error": str(e)}), 500
    
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
