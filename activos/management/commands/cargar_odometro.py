import pandas as pd
from django.core.management.base import BaseCommand
from activos.models import Activo, RegistroCiclosSemanal

class Command(BaseCommand):
    help = 'Carga los datos de ciclos para los moldes desde un archivo Excel.'

    def add_arguments(self, parser):
        parser.add_argument('ruta_excel', type=str, help='La ruta al archivo Excel a procesar.')
        parser.add_argument('nombre_hoja', type=str, help='El nombre de la hoja a leer (ej: Odometro).')

    def handle(self, *args, **kwargs):
        ruta_archivo = kwargs['ruta_excel']
        nombre_hoja = kwargs['nombre_hoja']
        
        self.stdout.write(self.style.NOTICE(f'Iniciando la carga desde "{ruta_archivo}" (Hoja: {nombre_hoja})'))

        try:
            df = pd.read_excel(ruta_archivo, sheet_name=nombre_hoja)
            
            df_moldes = df[df['TIPO ACTIVO'] == 'MOLD'].copy()
            self.stdout.write(f'Se encontraron {len(df_moldes)} registros de MOLDES.')

            df_moldes['fecha'] = pd.to_datetime(df_moldes['CICLO INICIAL'])
            df_moldes['año'] = df_moldes['fecha'].dt.isocalendar().year
            df_moldes['semana'] = df_moldes['fecha'].dt.isocalendar().week

            for _, row in df_moldes.iterrows():
                codigo_activo = row['NUMERO ACTIVO']
                ciclos_semanales = row['MEDIDOR']
                
                try:
                    activo_obj = Activo.objects.get(codigo=codigo_activo)
                    
                    RegistroCiclosSemanal.objects.update_or_create(
                        activo=activo_obj,
                        año=row['año'],
                        semana=row['semana'],
                        defaults={'ciclos': ciclos_semanales}
                    )
                    self.stdout.write(f"Registro procesado para {codigo_activo} - Semana {row['semana']}")
                
                except Activo.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'ADVERTENCIA: Activo {codigo_activo} no existe. Se omitirá.'))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR('Error: El archivo no se encontró.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ocurrió un error: {e}'))

        self.stdout.write(self.style.SUCCESS('Proceso finalizado.'))