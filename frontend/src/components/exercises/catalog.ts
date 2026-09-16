// Catálogo de ejercicios: nombre es-ES, búsqueda de vídeo de técnica y
// pictograma animado propio (2 fotogramas SVG, sin GIFs de terceros).
// Mantener slugs en sintonía con backend/app/services/wod_structure.py (EXERCISES).

interface Meta { name: string; pict: string; query: string; desc?: string; how?: string[] }

export const EXERCISES: Record<string, Meta> = {
  run: { name: 'Carrera', pict: 'run', query: 'hyrox running pace technique', desc: 'Carrera a pie al ritmo indicado.', how: ['Cadencia alta y pasos cortos', 'Tronco ligeramente inclinado adelante', 'Tras estación: primeros 200 m controlados y recupera el ritmo'] },
  ski_erg: { name: 'SkiErg', pict: 'ski_erg', query: 'hyrox skierg technique', desc: 'Máquina de esquí: tirón de brazos y core hacia abajo.', how: ['Brazos arriba, cae con el peso del cuerpo', 'Latigazo de core: abdomen fuerte al bajar', 'Termina el tirón junto a los muslos y vuelve fluido'] },
  sled_push: { name: 'Sled Push', pict: 'sled_push', query: 'hyrox sled push technique', desc: 'Empujar el trineo cargado por la calle marcada.', how: ['Brazos extendidos, cadera baja', 'Pasos cortos y rápidos, sin saltar', 'Empuja continuo: parar cuesta el doble'] },
  sled_pull: { name: 'Sled Pull', pict: 'sled_pull', query: 'hyrox sled pull technique', desc: 'Arrastrar el trineo hacia ti con cuerda.', how: ['Cuerpo atrás, peso en talones', 'Tira con dorsal y cadera, no solo brazos', 'Mano sobre mano sin pausa'] },
  burpee_broad_jump: { name: 'Burpee Broad Jump', pict: 'burpee_broad_jump', query: 'hyrox burpee broad jump technique', desc: 'Burpee + salto horizontal, avanzando.', how: ['Pecho al suelo en cada burpee', 'Salto largo con ambos pies', 'Ritmo sostenible: es la estación que más dispara el pulso'] },
  row: { name: 'Remo', pict: 'row', query: 'hyrox rowing 1000m technique', desc: 'Remoergómetro.', how: ['Orden: piernas → cadera → brazos', 'Vuelta al frente lenta (brazos-cadera-piernas)', 'Ritmo conservador: ~ritmo de 2k'] },
  farmers_carry: { name: 'Farmers Carry', pict: 'farmers_carry', query: 'hyrox farmers carry technique', desc: 'Caminar con una kettlebell en cada mano.', how: ['Hombros atrás, core apretado', 'Pasos rápidos y cortos', 'Agarre firme; si sueltas, para donde marca la norma'] },
  sandbag_lunges: { name: 'Sandbag Lunges', pict: 'sandbag_lunges', query: 'hyrox sandbag lunges technique', desc: 'Zancadas con saco sobre los hombros.', how: ['Saco sobre trapecios, no en el cuello', 'Rodilla trasera roza el suelo (sin rebotar)', 'Pierna adelantada empuja con glúteo'] },
  wall_balls: { name: 'Wall Balls', pict: 'wall_balls', query: 'hyrox wall balls technique', desc: 'Sentadilla + lanzar el balón a la diana.', how: ['Sentadilla completa (cadera bajo rodilla)', 'Lanza con el impulso de las piernas', 'Tandas grandes con micro-pausas > series al fallo'] },
  burpee: { name: 'Burpees', pict: 'burpee', query: 'burpee technique', desc: 'Pecho al suelo y salto con palmada arriba.', how: ['Baja de golpe, pecho al suelo', 'Sube y salta extendiendo cadera', 'Respira en el salto'] },
  squat: { name: 'Sentadilla', pict: 'squat', query: 'air squat technique', desc: 'Sentadilla sin peso.', how: ['Pies al ancho de hombros', 'Cadera atrás y abajo, rodillas fuera', 'Pecho alto todo el rato'] },
  front_squat: { name: 'Sentadilla frontal', pict: 'squat', query: 'front squat technique', desc: 'Sentadilla con barra apoyada delante, sobre hombros.', how: ['Codos altos, barra sobre deltoides', 'Baja vertical con core fuerte', 'Empuja el suelo al subir'] },
  thruster: { name: 'Thruster', pict: 'thruster', query: 'thruster technique', desc: 'Sentadilla frontal + press por encima de la cabeza, encadenados.', how: ['Baja a sentadilla completa', 'Usa el impulso de subida para el press', 'Barra acaba sobre la cabeza, brazos bloqueados'] },
  deadlift: { name: 'Peso muerto', pict: 'deadlift', query: 'deadlift technique', desc: 'Levantar la barra del suelo con la cadera.', how: ['Espalda neutra SIEMPRE', 'Empuja el suelo, la barra pegada a las piernas', 'Bloquea arriba con glúteo, sin hiperextender'] },
  kb_swing: { name: 'KB Swing', pict: 'kb_swing', query: 'kettlebell swing technique', desc: 'Balanceo de kettlebell con golpe de cadera.', how: ['Es un empuje de CADERA, no de brazos', 'La kettlebell sube sola hasta el pecho', 'Espalda neutra, core fuerte'] },
  box_jump: { name: 'Box Jump', pict: 'box_jump', query: 'box jump technique', desc: 'Salto al cajón.', how: ['Balanceo de brazos y salta', 'Aterriza suave con toda la planta', 'Extiende la cadera arriba; baja con paso, no de salto'] },
  press: { name: 'Press hombro', pict: 'press', query: 'overhead press technique', desc: 'Empujar la barra desde los hombros hasta arriba.', how: ['Core y glúteo apretados', 'La barra sube pegada a la cara', 'Bloquea con la cabeza "a través" de los brazos'] },
  pull_up: { name: 'Dominadas', pict: 'pull_up', query: 'pull up technique', desc: 'Colgado de la barra, sube hasta pasar la barbilla.', how: ['Empieza colgado con escápulas activas', 'Tira con dorsal, codos hacia el bolsillo', 'Baja controlado a brazos rectos'] },
  plank: { name: 'Plancha', pict: 'plank', query: 'plank technique', desc: 'Aguantar el cuerpo recto sobre antebrazos.', how: ['Cuerpo en línea, sin arquear ni levantar el culo', 'Glúteo y abdomen apretados', 'Respira: no aguantes el aire'] },
  carry: { name: 'Acarreo', pict: 'farmers_carry', query: 'loaded carry technique', desc: 'Caminar con carga (saco, kettlebells, disco).', how: ['Postura alta, core fuerte', 'Pasos cortos y estables'] },
  bike_erg: { name: 'BikeErg', pict: 'bike_erg', query: 'bike erg technique', desc: 'Bicicleta estática de aire.', how: ['Cadencia 80-95 rpm', 'Cuerpo estable, sin balanceo'] },
  mobility: { name: 'Movilidad', pict: 'mobility', query: 'movilidad para hyrox', desc: 'Trabajo de rango de movimiento.', how: ['Movimientos lentos y controlados', 'Sin dolor agudo: molestia suave sí, pinchazo no'] },
  // --- Movilidad / calentamiento con nombre propio ---
  ninety_ninety: { name: '90-90 de cadera', pict: 'ninety_ninety', query: '90 90 hip stretch como hacer', desc: 'Sentado con ambas rodillas dobladas a 90°: una pierna delante y otra al lado. Estira glúteo y rotadores de cadera.', how: ['Siéntate: pierna delantera a 90°, trasera a 90° hacia el lado', 'Espalda recta, inclínate sobre la pierna delantera', 'Respira lento; cambia de lado a mitad de tiempo'] },
  cat_camel: { name: 'Gato-camello', pict: 'cat_camel', query: 'cat camel gato camello espalda', desc: 'A cuatro patas, arquear y redondear la espalda alternando. Moviliza toda la columna.', how: ['A cuatro patas, manos bajo hombros', 'GATO: redondea la espalda mirando al ombligo', 'CAMELLO: arquea dejando caer el abdomen y mira al frente', 'Lento, siguiendo la respiración'] },
  glute_bridge: { name: 'Puente de glúteo', pict: 'glute_bridge', query: 'puente de gluteo tecnica', desc: 'Tumbado boca arriba, subir la cadera apretando el glúteo. Activa el glúteo y descarga el psoas.', how: ['Tumbado, pies cerca del culo', 'Sube la cadera apretando glúteo (no lumbar)', 'Pausa 1-2s arriba y baja controlado'] },
  hip_flexor_stretch: { name: 'Flexor de cadera en zancada', pict: 'hip_flexor_stretch', query: 'estiramiento psoas zancada rodilla suelo', desc: 'Rodilla trasera al suelo, cadera adelante: estira el psoas/flexor de la pierna atrasada.', how: ['Zancada con rodilla trasera apoyada', 'Aprieta el glúteo trasero y lleva la cadera adelante', 'No arquees la lumbar; siente el tirón delante de la cadera'] },
  thoracic_opener: { name: 'Apertura torácica', pict: 'thoracic_opener', query: 'thoracic rotation apertura torácica cuadrupedia', desc: 'A cuatro patas, mano en la nuca y girar el torso abriendo el codo al techo. Moviliza la espalda alta.', how: ['A cuatro patas, una mano en la nuca', 'Gira llevando el codo al techo, mirada sigue al codo', 'Vuelve pasando el codo hacia el brazo de apoyo'] },
  dead_bug: { name: 'Bicho muerto', pict: 'dead_bug', query: 'dead bug tecnica core', desc: 'Boca arriba, extender brazo y pierna contrarios sin despegar la lumbar. Core sin dañar la espalda.', how: ['Boca arriba: brazos al techo, rodillas a 90°', 'Baja brazo y pierna CONTRARIOS a la vez', 'Lumbar pegada al suelo siempre; vuelve y cambia'] },
  bird_dog: { name: 'Perro-pájaro', pict: 'bird_dog', query: 'bird dog tecnica', desc: 'A cuatro patas, extender brazo y pierna contrarios manteniendo la espalda estable.', how: ['A cuatro patas, espalda neutra', 'Extiende brazo y pierna contrarios hasta la horizontal', 'Sin girar la cadera; pausa 2s y cambia'] },
  cossack_squat: { name: 'Sentadilla cosaca', pict: 'cossack_squat', query: 'cossack squat tecnica', desc: 'Sentadilla lateral: todo el peso sobre una pierna, la otra estirada al lado.', how: ['Pies muy separados', 'Baja hacia un lado con talón apoyado', 'La otra pierna recta, punta arriba; alterna'] },
  leg_swing: { name: 'Balanceo de pierna', pict: 'leg_swing', query: 'leg swings calentamiento', desc: 'De pie, balancear una pierna adelante-atrás (o en cruz). Suelta cadera antes de correr.', how: ['Apóyate en pared o poste', 'Balancea la pierna relajada, amplitud creciente', '10-15 por pierna; luego en cruz si toca'] },
  inchworm: { name: 'Oruga', pict: 'inchworm', query: 'inchworm ejercicio', desc: 'De pie, caminar con las manos hasta plancha y volver. Calienta isquios, hombros y core.', how: ['Flexiona y apoya las manos', 'Camina con las manos hasta plancha', 'Vuelve caminando con las manos a los pies y levántate'] },
  worlds_greatest: { name: 'El mejor estiramiento del mundo', pict: 'worlds_greatest', query: 'worlds greatest stretch como hacer', desc: 'Zancada profunda + codo al suelo + giro de torso. Tres estiramientos en uno: cadera, isquio y torácica.', how: ['Zancada larga, manos dentro del pie delantero', 'Codo del lado del pie hacia el suelo', 'Gira y abre el brazo al techo; cambia de lado'] },
  ankle_rock: { name: 'Movilidad de tobillo', pict: 'ankle_rock', query: 'ankle mobility pared rodilla', desc: 'Rodilla hacia la pared sin levantar el talón. Prepara el tobillo para sentadillas y zancadas.', how: ['Pie a un palmo de la pared', 'Lleva la rodilla a la pared SIN despegar el talón', 'Si toca fácil, aleja el pie un poco'] },
  lunge: { name: 'Zancada', pict: 'sandbag_lunges', query: 'zancada tecnica', desc: 'Paso largo al frente bajando la rodilla trasera.', how: ['Paso largo, tronco vertical', 'Rodilla trasera roza el suelo', 'Empuja con el talón delantero para subir'] },
  jumping_jack: { name: 'Jumping jacks', pict: 'jumping_jack', query: 'jumping jacks', desc: 'Saltos abriendo y cerrando piernas y brazos. Para subir pulsaciones.', how: ['Salta abriendo piernas y subiendo brazos', 'Vuelve cerrando; ritmo constante'] },
  other: { name: 'Ejercicio', pict: 'other', query: '', desc: 'Ejercicio fuera del catálogo: mira las notas del entreno.', how: [] },
}

export function exerciseMeta(slug: string, name?: string | null): { label: string; pict: string; videoUrl: string | null } {
  const m = EXERCISES[slug] || EXERCISES.other
  const label = slug === 'other' && name ? name : m.name
  const q = slug === 'other' && name ? `${name} technique` : m.query
  return {
    label,
    pict: m.pict,
    videoUrl: q ? `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}` : null,
  }
}

