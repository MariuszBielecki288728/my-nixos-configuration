{
  # Public key for the installed non-root administrator account.
  my.ssh.authorizedKeys = [
    "ssh-ed25519 REPLACE_WITH_REAL_PUBLIC_KEY admin"
  ];
  # Public key for temporary root access in the non-destructive rescue system.
  my.rescue.authorizedKeys = [
    "ssh-ed25519 REPLACE_WITH_REAL_PUBLIC_KEY rescue-access"
  ];
}
