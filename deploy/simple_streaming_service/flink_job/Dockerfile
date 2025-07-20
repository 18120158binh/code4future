FROM flink:1.20.0-scala_2.12-java11

# Install Python3 & pip
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*

# Install PyFlink
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Add Kafka connector JAR for Flink
RUN wget -P /opt/flink/lib/ https://repo1.maven.org/maven2/org/apache/flink/flink-connector-kafka/3.3.0-1.20/flink-connector-kafka-3.3.0-1.20.jar \
 && wget -P /opt/flink/lib/ https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.5.1/kafka-clients-3.5.1.jar \
 && wget -P /opt/flink/lib/ https://repo1.maven.org/maven2/org/apache/flink/flink-connector-jdbc/3.3.0-1.20/flink-connector-jdbc-3.3.0-1.20.jar \
 && wget -P /opt/flink/lib/ https://repo1.maven.org/maven2/mysql/mysql-connector-java/8.0.30/mysql-connector-java-8.0.30.jar

# Copy job
COPY job.py /opt/flink/usrlib/job.py

CMD ["python3", "/opt/flink/usrlib/job.py"]
