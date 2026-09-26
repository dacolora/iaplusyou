"""
Modo «Flow Plus» de Crear. `refinador` guarda cada prompt (texto original,
vigente con versión, fragmentos fijos), su hilo con Claude para corregirlo
antes de generar, las reglas que no se negocian y la aprobación. `rutas` es
el Blueprint JSON que usa la pestaña. Se llama `guiones` porque `flowplus_*`
ya nombra el pipeline de Crear que existía.
"""
