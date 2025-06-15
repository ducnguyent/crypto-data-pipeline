#!/bin/bash

# Download required Spark jars
mkdir -p spark/jars

echo "Downloading Hudi Spark bundle..."
wget -O spark/jars/hudi-spark3.4-bundle_2.12-0.14.0.jar \
  https://repo1.maven.org/maven2/org/apache/hudi/hudi-spark3.4-bundle_2.12/0.14.0/hudi-spark3.4-bundle_2.12-0.14.0.jar

echo "Downloading AWS SDK..."
wget -O spark/jars/aws-java-sdk-bundle-1.12.367.jar \
  https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.367/aws-java-sdk-bundle-1.12.367.jar

echo "Downloading Hadoop AWS..."
wget -O spark/jars/hadoop-aws-3.3.4.jar \
  https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar

echo "All Spark jars downloaded successfully!"