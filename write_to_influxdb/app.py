import os
import json
from datetime import datetime
import boto3
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

'''
Listens to SNS events from NewFetchObjects,
gets the new S3 object,
convert them to line protocol format
write to InfluxDB
'''

influxdb_url = os.environ['INFLUXDB_URL'] 
influxdb_bucket_name = os.environ['INFLUXDB_BUCKET_NAME']
influxdb_org = os.environ['INFLUXDB_ORG']
influxdb_token = os.environ['INFLUXDB_TOKEN']
influxdb_measurement_name = os.environ['INFLUXDB_MEASUREMENT_NAME']

tagset_headers = 'location,city,country,parameter,unit'.split(',')
fieldset_headers = 'value'.split(',')

s3 = boto3.client('s3')
influx = InfluxDBClient(url=influxdb_url, token=influxdb_token, org=influxdb_org)

def fetch_result_to_lineprotocol(result):
    lines = result.decode().strip().split('\n')
    for json_str_line in lines:
        row = json.loads(json_str_line)
        tagset = []
        tags = {}
        fieldset = []
        fields = {}
        for tag_name in tagset_headers:
            tag_value = row[tag_name]
            tagset.append(f'{tag_name}={tag_value}')
            tags[tag_name] = row[tag_name]
        for field_name in fieldset_headers:
            fieldset.append(f'{field_name}={row[field_name]}')
            fields[field_name] = row[field_name]

        timestamp = datetime.strptime(row['date']['utc'], "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
        timestamp = int(timestamp) * 1_000_000_000  # to nanoseconds

        line = f'{influxdb_measurement_name},{",".join(tagset)} {",".join(fieldset)} {timestamp}'
        obj = {
            'measurement': influxdb_measurement_name,
            'tags': tags,
            'fields': fields,
            'time': timestamp 
        }
        yield obj

def lambda_handler(event, context):
    message = event['Records'][0]['Sns']['Message']
    message = json.loads(message)
    s3_info = message['Records'][0]['s3']
    s3_bucket = s3_info['bucket']['name']
    s3_object_key = s3_info['object']['key']

    # for local debug
    # s3_bucket = 'openaq-fetches'
    # s3_object_key = 'realtime/2020-06-11/1591879264.ndjson'
    
    print('S3 object: ', s3_object_key)

    response = s3.get_object(Bucket=s3_bucket, Key=s3_object_key)
    fetch_result = response['Body'].read()
    lines = list(fetch_result_to_lineprotocol(fetch_result))

    write_api = influx.write_api(write_options=SYNCHRONOUS)
    write_api.write(influxdb_bucket_name, influxdb_org, lines)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": f"Inserted {len(lines)} items to InfluxDB bucket {influxdb_bucket_name}",
        }),
    }
