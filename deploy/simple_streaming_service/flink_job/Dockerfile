# 1. Start with the official Flink image with Python support
# Make sure the version matches the connectors you will use
FROM flink:1.19

# Install Python 3 and pip
RUN apt-get update -y && \
    apt-get install -y python3 python3-pip && \
    ln -s /usr/bin/python3 /usr/bin/python

# Copy and install the Python dependencies
# This step is cached by Docker as long as requirements.txt doesn't change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy all connector JARs into Flink's main library folder so they are auto-loaded.
COPY ./jars/ /opt/flink/lib/

# Set a working directory for our application files
WORKDIR /app