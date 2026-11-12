output "bucket" {
  value = aws_s3_bucket.exports.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.exports.arn
}
