// All editable product content lives here: names, finishes, sample price and chapter copy.

export type ColorwayId = 'graphite' | 'silver' | 'ember';

export interface Colorway {
  id: ColorwayId;
  name: string;
  description: string;
  /** Swatch colours used by the HTML interface: shell, then grip. */
  swatch: [string, string];
  /** Material values used by the 3D scene. */
  shell: string;
  shellMetal: number;
  shellRough: number;
  grip: string;
  spine: string;
  spineRough: number;
}

export const PRODUCT = {
  name: 'ARC',
  fullName: 'ARC controller concept',
  /** Sample price for the demo cart. No real checkout exists. */
  price: 189,
  currency: 'USD',
};

export const COLORWAYS: Colorway[] = [
  {
    id: 'graphite',
    name: 'Graphite',
    description: 'Micro-textured graphite shell, satin titanium spine.',
    swatch: ['#2a2e35', '#8e9196'],
    shell: '#1c1f24',
    shellMetal: 0,
    shellRough: 0.52,
    grip: '#131518',
    spine: '#707378',
    spineRough: 0.42,
  },
  {
    id: 'silver',
    name: 'Silver',
    description: 'Bead-blasted aluminium-look shell, dark titanium spine.',
    swatch: ['#b5b9bf', '#3e4248'],
    shell: '#a3a7ad',
    shellMetal: 1,
    shellRough: 0.42,
    grip: '#17191c',
    spine: '#3e4147',
    spineRough: 0.3,
  },
  {
    id: 'ember',
    name: 'Ember',
    description: 'Burnt-orange shell, graphite grips, titanium spine.',
    swatch: ['#a2431a', '#22252a'],
    shell: '#6b2a0e',
    shellMetal: 0,
    shellRough: 0.5,
    grip: '#15171a',
    spine: '#707378',
    spineRough: 0.42,
  },
];

export const getColorway = (id: string): Colorway => COLORWAYS.find((c) => c.id === id) ?? COLORWAYS[0];

/** Scroll chapters after the opening view. Each copy block names something the model really has. */
export const STAGES = [
  {
    id: 'detail',
    label: 'Sticks',
    title: 'Every detail, considered.',
    body: 'Concave stick caps with a dimpled rubber top sit low in dark wells moulded into the shell.',
  },
  {
    id: 'controls',
    label: 'Controls',
    title: 'Set into the shell.',
    body: 'A satin metal cross pad, low-profile face buttons and a titanium spine with flush centre keys and an amber status light.',
  },
  {
    id: 'rear',
    label: 'Shoulders',
    title: 'Shaped around the hands.',
    body: 'Bumpers follow the shoulders, each trigger has a finger scoop and sits in its own recess, and pebbled rubber grips taper outward.',
  },
] as const;

/** "Designed in layers": the exterior parts shown in the exploded render, in its left-to-right order. */
export const LAYERS = [
  {
    id: 'spine',
    label: 'Spine',
    title: 'Centre spine',
    material: 'Brushed titanium',
    body: 'One strip of titanium runs down the face between the sticks. It joins the two halves of the face and carries the centre keys and the amber status light, set flush with its surface.',
    finishes: 'Satin titanium on Graphite and Ember, dark titanium on Silver.',
  },
  {
    id: 'shell',
    label: 'Shell',
    title: 'Shell',
    material: 'Micro-textured polymer, front and back halves',
    body: 'The two halves close on a single 0.3 mm parting line around the widest edge. Edges are tight across the face and fuller where the shell meets your palms. A fine surface texture gives the shell a matte, even finish.',
    finishes: 'Graphite, Silver or Ember.',
  },
  {
    id: 'grips',
    label: 'Grips',
    title: 'Grips',
    material: 'Pebbled rubber, separate parts',
    body: 'Rubber grips wrap the back of each handle, where your fingers rest. They are drawn as separate parts with a pebbled texture, which sets the grip areas apart from the smooth shell.',
    finishes: 'Graphite on every finish.',
  },
] as const;

/** "Why ARC": the design intention, in about fifty words. */
export const WHY = {
  title: 'Why ARC.',
  body: 'ARC is a design study in keeping a controller familiar. The sticks, cross pad and buttons sit where your thumbs expect them; the work went into everything around them: a sculpted shell, a single titanium spine, quiet detailing and three finishes, Graphite, Silver and Ember, each with its own character.',
  alt: 'ARC in Silver resting on a dark desk at night, a keyboard and a monitor softly out of focus behind it, lit by a blue light strip along the wall.',
};

/**
 * Footer credit. Add the creator's name to show "Concept and design by <name>"; left empty, the footer shows
 * only how the project was made.
 */
export const CREDIT = {
  creator: '',
  made: 'Model, renders and site built with Blender, React and AI coding tools. The desk backdrop in the setup image was generated with ForgeGUI.',
};

export const formatPrice =(value: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: PRODUCT.currency }).format(value);
