FROM flink:1.19.3

RUN apt-get update -y && \
    apt-get install -y python3 python3-pip && \
    ln -s /usr/bin/python3 /usr/bin/python

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./jars/ /opt/flink/lib/

# Iceberg Flink Runtime (matches Flink 1.17)
RUN wget https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-flink-runtime-1.19/1.9.0/iceberg-flink-runtime-1.19-1.9.0.jar -P /opt/flink/lib/
RUN wget https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-aws-bundle/1.9.0/iceberg-aws-bundle-1.9.0.jar -P /opt/flink/lib/
# Hadoop 3.3.4 core libs
RUN wget https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-common/3.3.4/hadoop-common-3.3.4.jar -P /opt/flink/lib/
RUN wget https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-hdfs/3.3.4/hadoop-hdfs-3.3.4.jar -P /opt/flink/lib/
RUN wget https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-client/3.3.4/hadoop-client-3.3.4.jar -P /opt/flink/lib/
RUN wget https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-auth/3.3.4/hadoop-auth-3.3.4.jar -P /opt/flink/lib/
RUN wget https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar -P /opt/flink/lib/
RUN wget https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-hdfs-client/3.3.4/hadoop-hdfs-client-3.3.4.jar -P /opt/flink/lib/
# AWS SDK bundle for Hadoop-AWS
RUN wget https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.11.1026/aws-java-sdk-bundle-1.11.1026.jar -P /opt/flink/lib/
# Flink S3 FS Hadoop (must match your Flink version)
RUN wget https://repo1.maven.org/maven2/org/apache/flink/flink-s3-fs-hadoop/1.19.0/flink-s3-fs-hadoop-1.19.0.jar -P /opt/flink/lib/

WORKDIR /app