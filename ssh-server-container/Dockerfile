# Use Ubuntu as the base image
FROM ubuntu:latest

# Install OpenSSH server and sudo
RUN apt-get update && apt-get install -y openssh-server sudo

# Create a user with passwordless sudo
RUN useradd -m -s /bin/bash user && \
    echo 'user:test' | chpasswd && \
    echo 'user ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# Set up SSH keys and start the SSH service
RUN mkdir /var/run/sshd

COPY ca.pub /etc/ssh/ca.pub

# Expose port 22 (SSH port)
EXPOSE 22

# Allow password authentication (for simplicity in this example)
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
RUN echo "PermitRootLogin yes" >> /etc/ssh/sshd_config
RUN echo "TrustedUserCAKeys /etc/ssh/ca.pub" >> /etc/ssh/sshd_config
RUN echo "PermitTTY yes" >> /etc/ssh/sshd_config

# Start SSH server
CMD ["/usr/sbin/sshd", "-D"]
