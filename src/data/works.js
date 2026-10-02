// Портфолио на главной. Карточка показывается, только если у неё есть настоящее фото:
// положите снимок в assets/works/ и укажите путь в photo, например "/assets/works/shkaf-niche.jpg".
export const WORKS = [
  { idx: "01", cls: "shot shot--a", title: "Встроенный шкаф", sub: "Ниша у окна · матовый шпон", photo: "" },
  { idx: "02", cls: "shot", title: "Кухня", sub: "Матовый графит · ящики до потолка", photo: "" },
  { idx: "03", cls: "shot", title: "Кровать", sub: "Изголовье 180 · велюр", photo: "" },
  { idx: "04", cls: "shot", title: "Шкаф в спальню", sub: "Шпон дуба · скрытые ручки", photo: "" },
  { idx: "05", cls: "shot", title: "Кухня с островом", sub: "Камень на столешнице · фасады без блеска", photo: "" },
  { idx: "06", cls: "shot", title: "Прихожая", sub: "Банкетка, зеркало, обувь", photo: "" },
  { idx: "07", cls: "shot", title: "Детская", sub: "Система хранения по росту", photo: "" },
  { idx: "08", cls: "shot shot--h", title: "ТВ-зона", sub: "Низкий комод · скрытые ниши под технику", photo: "" },
];

export const PUBLISHED_WORKS = WORKS.filter((item) => item.photo);
