class rabbitmq {
  package { 'rabbitmq-server':
    ensure => installed,
  }
}
