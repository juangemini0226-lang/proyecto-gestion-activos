from django.shortcuts import render

def escaner_qr(request):
    # Esta vista simplemente muestra la página con el lector.
    return render(request, 'lector_qr/escaner.html')