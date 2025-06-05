FROM openjdk:11-jre-slim

ARG KYUUBI_VERSION=1.5.0-incubating

# Install Kyuubi
RUN apt-get update && apt-get install -y wget && \
    wget https://downloads.apache.org/incubator/kyuubi/${KYUUBI_VERSION}/apache-kyuubi-${KYUUBI_VERSION}-bin.tgz && \
    tar -xzf apache-kyuubi-${KYUUBI_VERSION}-bin.tgz && \
    mv apache-kyuubi-${KYUUBI_VERSION}-bin /opt/kyuubi && \
    rm apache-kyuubi-${KYUUBI_VERSION}-bin.tgz && \
    apt-get remove -y wget && apt-get clean

# Set environment variables
ENV KYUUBI_HOME=/opt/kyuubi
ENV PATH=$KYUUBI_HOME/bin:$PATH

# Copy Kyuubi configuration files
COPY kyuubi.conf $KYUUBI_HOME/conf/kyuubi.conf
COPY hadoop-config/* /etc/hadoop/conf/

# Expose the port Kyuubi server listens on
EXPOSE 10009

CMD ["kyuubi", "start"]
