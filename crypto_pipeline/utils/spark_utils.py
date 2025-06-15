import logging
from pyspark.sql import SparkSession
from typing import Dict, Any

logger = logging.getLogger(__name__)


def get_spark_session(app_name: str = "CryptoPipeline") -> SparkSession:
    """Create Spark session configured for Hudi and S3"""

    spark = SparkSession.builder \
        .appName(app_name) \
        .master("spark://spark-master:7077") \
        .config("spark.executor.memory", "2g") \
        .config("spark.executor.cores", "2") \
        .config("spark.driver.memory", "1g") \
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer") \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.sql.extensions", "org.apache.spark.sql.hudi.HoodieSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.hudi.catalog.HoodieCatalog") \
        .config("spark.kryo.registrator", "org.apache.spark.HoodieSparkKryoRegistrar") \
        .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000") \
        .config("spark.hadoop.fs.s3a.access.key", "admin") \
        .config("spark.hadoop.fs.s3a.secret.key", "password123") \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .getOrCreate()

    logger.info(f"Spark session created: {spark.sparkContext.applicationId}")
    return spark


def get_hudi_write_config(table_name: str, operation: str = "upsert") -> Dict[str, str]:
    """Get Hudi write configuration"""
    return {
        'hoodie.table.name': table_name,
        'hoodie.datasource.write.recordkey.field': 'record_id',
        'hoodie.datasource.write.partitionpath.field': 'symbol,date',
        'hoodie.datasource.write.precombine.field': 'event_time',
        'hoodie.datasource.write.operation': operation,
        'hoodie.datasource.write.table.type': 'COPY_ON_WRITE',
        'hoodie.upsert.shuffle.parallelism': '4',
        'hoodie.insert.shuffle.parallelism': '4',
        'hoodie.datasource.write.hive_style_partitioning': 'true'
    }
