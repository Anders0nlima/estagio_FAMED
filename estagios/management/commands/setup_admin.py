from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
import os

class Command(BaseCommand):
    help = 'Cria o usuário administrador padrão caso não exista'

    def handle(self, *args, **options):
        username = os.environ.get('ADMIN_USERNAME', 'diretor')
        password = os.environ.get('ADMIN_PASSWORD', 'diretor123')
        email = os.environ.get('ADMIN_EMAIL', 'diretor@ufpa.br')

        user, created = User.objects.get_or_create(username=username, defaults={'email': email})
        if created:
            user.set_password(password)
            user.is_superuser = True
            user.is_staff = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Usuário administrador '{username}' criado com sucesso!"))
        else:
            self.stdout.write(f"Usuário administrador '{username}' já existe no banco.")
