# Terraform

Directorio para la infraestructura como código del proyecto.

```text
terraform/
├── environments/  # Configuración raíz por entorno
└── modules/       # Módulos reutilizables
```

Los módulos raíz de cada entorno se añadirán en `environments/` cuando se definan los entornos de despliegue. Los componentes reutilizables irán en `modules/`.

Esta estructura no fija proveedor cloud, servicios, backend de estado ni configuración de despliegue; esos detalles se decidirán antes de añadir archivos `.tf`.
